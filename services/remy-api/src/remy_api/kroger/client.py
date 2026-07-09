"""Thin async HTTP client for the Kroger Public API (https://api.kroger.com/v1).

Design choice: a direct ``httpx.AsyncClient`` rather than wrapping the sync
``kroger-api`` SDK. Our needs are narrow (four endpoint families) and everything
else in remy-api is async, so a native async client avoids ``asyncio.to_thread``
hops and gives us first-class control over token caching, error mapping, and the
401→refresh→retry path.

Two token contexts (PRD §7.2):

* **Client-credentials app token** (``product.compact``) for products/locations,
  cached in-memory on the client instance with its expiry.
* **Per-user OAuth token** for cart writes — this client only performs the token
  *exchange/refresh* over HTTP and returns a :class:`KrogerTokenBundle`; the
  service layer owns reading/persisting those to the encrypted ``kroger_tokens``
  table (the single token store).

**The Kroger cart API is add-only**: ``PUT /cart/add`` is the only cart
operation available on the Public API. There is no endpoint to read, remove
from, or clear the real cart, and none to check out (FR-18).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx

from remy_api.config import get_settings

from .errors import KrogerAPIError, KrogerAuthError, KrogerRateLimitError
from .models import FULFILLMENT_FILTER, KrogerTokenBundle

KROGER_API_BASE = "https://api.kroger.com/v1"
DEFAULT_SCOPES = "product.compact cart.basic:write"
APP_SCOPE = "product.compact"
# Refresh the app/user token a little early so a request never races the expiry.
TOKEN_SKEW_SECONDS = 60


def generate_pkce() -> tuple[str, str]:
    """Return ``(code_verifier, code_challenge)`` for the S256 PKCE flow.

    The verifier is a high-entropy URL-safe string; the challenge is the
    base64url-encoded SHA-256 of the verifier with padding stripped (RFC 7636).
    """
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def generate_state() -> str:
    return secrets.token_urlsafe(32)


class KrogerClient:
    """Stateless w.r.t. user tokens; caches only the shared app token."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or KROGER_API_BASE).rstrip("/")
        self.client_id = client_id if client_id is not None else settings.kroger_client_id
        self.client_secret = client_secret if client_secret is not None else settings.kroger_client_secret
        self.redirect_uri = redirect_uri if redirect_uri is not None else settings.kroger_redirect_uri
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(20.0))
        self._owns_http = http is None
        self._app_token: str | None = None
        self._app_token_expiry: float = 0.0
        self._app_lock = asyncio.Lock()

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    # --- Authorize URL --------------------------------------------------------

    def build_authorize_url(self, *, state: str, code_challenge: str, scope: str = DEFAULT_SCOPES) -> str:
        params = {
            "scope": scope,
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{self.base_url}/connect/oauth2/authorize?{urlencode(params)}"

    # --- Token endpoint -------------------------------------------------------

    def _basic_auth(self) -> str:
        raw = f"{self.client_id}:{self.client_secret}".encode()
        return base64.b64encode(raw).decode("ascii")

    async def _token_request(self, form: dict[str, str]) -> KrogerTokenBundle:
        headers = {
            "Authorization": f"Basic {self._basic_auth()}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        try:
            resp = await self._http.post(f"{self.base_url}/connect/oauth2/token", data=form, headers=headers)
        except httpx.HTTPError as exc:
            raise KrogerAPIError(f"Kroger token request failed: {exc}") from exc
        if resp.status_code == 429:
            raise KrogerRateLimitError("Kroger rate limit hit on token endpoint.", retry_after=_retry_after(resp))
        if resp.status_code >= 400:
            # 400 invalid_grant / 401 → the credentials or grant are bad.
            detail = _error_detail(resp)
            raise KrogerAuthError(
                f"Kroger token exchange failed ({resp.status_code}): {detail}", status_code=resp.status_code
            )
        return KrogerTokenBundle.from_raw(resp.json())

    async def fetch_app_token(self) -> KrogerTokenBundle:
        return await self._token_request({"grant_type": "client_credentials", "scope": APP_SCOPE})

    async def exchange_code(self, code: str, code_verifier: str) -> KrogerTokenBundle:
        return await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
                "code_verifier": code_verifier,
            }
        )

    async def refresh(self, refresh_token: str) -> KrogerTokenBundle:
        return await self._token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})

    async def get_app_token(self) -> str:
        """Return a cached client-credentials access token, refreshing on expiry."""
        loop = asyncio.get_event_loop()
        if self._app_token and loop.time() < self._app_token_expiry:
            return self._app_token
        async with self._app_lock:
            if self._app_token and loop.time() < self._app_token_expiry:
                return self._app_token
            bundle = await self.fetch_app_token()
            self._app_token = bundle.access_token
            self._app_token_expiry = loop.time() + max(bundle.expires_in - TOKEN_SKEW_SECONDS, 0)
            return self._app_token

    # --- Data endpoints -------------------------------------------------------

    async def _get(self, path: str, *, access_token: str, params: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        try:
            resp = await self._http.get(f"{self.base_url}{path}", params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise KrogerAPIError(f"Kroger request to {path} failed: {exc}") from exc
        _raise_for_status(resp, path)
        return resp.json()

    async def get_locations_raw(
        self, *, zip_code: str, limit: int = 8, chain: str | None = None, radius_in_miles: int = 25
    ) -> dict[str, Any]:
        token = await self.get_app_token()
        params: dict[str, Any] = {
            "filter.zipCode.near": zip_code,
            "filter.limit": limit,
            "filter.radiusInMiles": radius_in_miles,
        }
        if chain:
            params["filter.chain"] = chain
        return await self._get("/locations", access_token=token, params=params)

    async def get_products_raw(
        self, *, term: str, location_id: str, limit: int = 10, fulfillment: str | None = None
    ) -> dict[str, Any]:
        token = await self.get_app_token()
        params: dict[str, Any] = {
            "filter.term": term,
            "filter.locationId": location_id,
            "filter.limit": limit,
        }
        if fulfillment:
            mapped = FULFILLMENT_FILTER.get(fulfillment)
            if mapped:
                params["filter.fulfillment"] = mapped
        return await self._get("/products", access_token=token, params=params)

    async def get_location_raw(self, location_id: str) -> dict[str, Any] | None:
        """Fetch one location; ``None`` if Kroger returns 404 (unknown store)."""
        token = await self.get_app_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        try:
            resp = await self._http.get(f"{self.base_url}/locations/{location_id}", headers=headers)
        except httpx.HTTPError as exc:
            raise KrogerAPIError(f"Kroger location lookup failed: {exc}") from exc
        if resp.status_code == 404:
            return None
        _raise_for_status(resp, f"/locations/{location_id}")
        return resp.json()

    async def put_cart_add(self, *, access_token: str, items: list[dict[str, Any]]) -> None:
        """Batch add to the real cart. Returns ``None`` on success (HTTP 204).

        Raises :class:`KrogerAuthError` on 401 so the caller can refresh + retry.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        try:
            resp = await self._http.put(f"{self.base_url}/cart/add", json={"items": items}, headers=headers)
        except httpx.HTTPError as exc:
            raise KrogerAPIError(f"Kroger cart write failed: {exc}") from exc
        _raise_for_status(resp, "/cart/add")


def _retry_after(resp: httpx.Response) -> int | None:
    value = resp.headers.get("Retry-After")
    if value and value.isdigit():
        return int(value)
    return None


def _error_detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except Exception:
        return resp.text[:200] if resp.text else ""
    if isinstance(body, dict):
        return str(body.get("error_description") or body.get("error") or body)[:200]
    return str(body)[:200]


def _raise_for_status(resp: httpx.Response, path: str) -> None:
    if resp.status_code < 400:
        return
    if resp.status_code == 401:
        raise KrogerAuthError(f"Kroger returned 401 for {path}.", status_code=401)
    if resp.status_code == 429:
        raise KrogerRateLimitError(f"Kroger rate limit hit on {path}.", retry_after=_retry_after(resp))
    raise KrogerAPIError(
        f"Kroger {path} returned {resp.status_code}: {_error_detail(resp)}", status_code=resp.status_code
    )
