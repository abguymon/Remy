"""Application configuration.

Settings load from the environment (and a local ``.env`` in development).
Security-critical secrets (``JWT_SECRET``, ``ENCRYPTION_KEY``) are validated
**fail-closed**: startup aborts with a clear message if they are missing,
empty, or a known placeholder value (PRD §6, §9.5).
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder tokens that must never survive into a running deployment. Matched
# case-insensitively as substrings so common template values are all rejected.
_PLACEHOLDER_MARKERS = (
    "change_me",
    "changeme",
    "your_",
    "_here",
    "placeholder",
    "example",
    "todo",
)


class ConfigError(RuntimeError):
    """Raised at startup when required configuration is missing or unsafe."""


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    api_title: str = "Remy API"
    api_version: str = "0.2.0"
    debug: bool = False

    # --- Auth & crypto (required, fail-closed) ---
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 168  # 7 days
    encryption_key: str = ""
    auth_rate_limit_window_seconds: int = 900
    auth_login_rate_limit: int = 10
    auth_registration_rate_limit: int = 5

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///data/remy.db"

    # --- Recipe images (T3) ---
    # Downloaded, re-encoded recipe images live here; never hotlinked (PRD §5).
    recipe_images_dir: str = "data/recipe-images"

    # --- Kroger ---
    kroger_client_id: str = ""
    kroger_client_secret: str = ""
    kroger_redirect_uri: str = "http://localhost:8080/kroger/callback"

    # --- LLM (provider-agnostic) ---
    # LiteLLM routes off the model string ("anthropic/...", "openai/...").
    llm_provider: str = "anthropic"
    llm_model: str = "anthropic/claude-sonnet-4-5"
    llm_temperature: float = 0.0
    llm_timeout: float = 60.0
    llm_max_retries: int = 0  # transport retries; validation retry is separate
    # --- Langfuse Cloud observability (optional) ---
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = "https://us.cloud.langfuse.com"
    langfuse_environment: str = "production"
    # Cost/token metadata is always traced when enabled. Prompt and response
    # content may contain personal data and requires an explicit opt-in.
    langfuse_capture_content: bool = False

    # --- Web search ---
    search_provider: str = "brave"  # brave | llm | searxng
    search_api_key: str = ""
    search_timeout: float = 10.0
    # Base URL of a self-hosted SearXNG instance (search_provider=searxng).
    # In the compose stack this is the internal service: http://searxng:8080
    searxng_url: str = ""

    # --- MCP facade ---
    mcp_facade_enabled: bool = True
    # DNS-rebinding protection for the MCP endpoint. Off by default: the facade
    # sits behind the reverse proxy and enforces its own bearer-token auth, and
    # the public Host header is not known at build time. Set these (comma- or
    # JSON-list) to your deploy domain to turn strict host/origin checks back on.
    mcp_allowed_hosts: list[str] = []
    mcp_allowed_origins: list[str] = []

    # --- Web app origin ---
    # Empty = relative OAuth-return redirects (single-origin prod behind Traefik).
    # Set to e.g. http://localhost:3000 in split-origin dev.
    web_app_url: str = ""

    # --- CORS (dev) ---
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    @field_validator("jwt_secret", "encryption_key")
    @classmethod
    def _require_secret(cls, value: str, info: ValidationInfo) -> str:
        name = info.field_name or "secret"
        if not value or not value.strip():
            raise ConfigError(
                f"{name.upper()} is required but missing or empty. "
                "Set a real value in .env (see .env.template). Refusing to start."
            )
        if _looks_like_placeholder(value):
            raise ConfigError(
                f"{name.upper()} is set to a placeholder value. "
                "Generate a real secret (see .env.template). Refusing to start."
            )
        return value

    @field_validator("encryption_key")
    @classmethod
    def _validate_fernet_key(cls, value: str) -> str:
        # Only reached once the required-secret check above has passed.
        try:
            Fernet(value.encode())
        except (ValueError, TypeError) as exc:
            raise ConfigError(
                "ENCRYPTION_KEY is not a valid Fernet key. Generate one with: "
                'python -c "from cryptography.fernet import Fernet; '
                'print(Fernet.generate_key().decode())". Refusing to start.'
            ) from exc
        return value


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance, validating fail-closed on first use.

    Raises :class:`ConfigError` with an actionable message if required secrets
    are missing or unsafe. Pydantic wraps validator errors in a
    ``ValidationError``; we unwrap the underlying :class:`ConfigError` so the
    startup message is clean.
    """
    from pydantic import ValidationError

    try:
        return Settings()
    except ValidationError as exc:
        for err in exc.errors():
            cause = err.get("ctx", {}).get("error")
            if isinstance(cause, ConfigError):
                raise cause from exc
        raise
