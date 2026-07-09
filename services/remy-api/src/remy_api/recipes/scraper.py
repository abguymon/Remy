"""Recipe URL parsing (FR-6): ``recipe-scrapers`` first, LLM fallback second.

Pipeline
--------
1. Fetch the page with httpx (browser-ish UA, 10s timeout, size cap).
2. Parse with ``recipe-scrapers`` in wild mode (schema.org / JSON-LD). If it
   yields a complete recipe (title + ingredients + instructions), use it.
3. Otherwise, if an LLM client is wired (T4), extract ``{title, image, yield,
   times, ingredients, instructions}`` from the page text via structured output.
4. If neither path produces a complete recipe, raise :class:`RecipeParseError`
   listing exactly what failed — never a silent empty success (PRD §9.1).
"""

from __future__ import annotations

import logging

import httpx
from bs4 import BeautifulSoup
from recipe_scrapers import scrape_html

from remy_api.recipes.llm_fallback import RecipeParseError, StructuredLLM, llm_extract_recipe
from remy_api.recipes.schemas import ParsedIngredient, ParsedRecipe

logger = logging.getLogger("remy.recipes.scraper")

# Browser-ish UA — many recipe sites 403 obvious bots.
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
_FETCH_TIMEOUT = 10.0  # seconds
_MAX_PAGE_BYTES = 3_000_000  # 3 MB hard cap on downloaded HTML
_MAX_TEXT_CHARS = 24_000  # cap the text handed to the LLM fallback


async def fetch_page(url: str, *, client: httpx.AsyncClient | None = None) -> str:
    """Fetch ``url`` and return its HTML, or raise :class:`RecipeParseError`.

    Enforces the timeout and a response-size cap; a page that is too large, a
    non-2xx status, or a transport error all become a typed parse error.
    """
    headers = {"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=_FETCH_TIMEOUT, follow_redirects=True, headers=headers)
    try:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        content = resp.content[: _MAX_PAGE_BYTES + 1]
        if len(content) > _MAX_PAGE_BYTES:
            raise RecipeParseError(
                "Recipe page is too large to parse safely.",
                reasons=["page_too_large"],
            )
        return content.decode(resp.encoding or "utf-8", errors="replace")
    except httpx.HTTPStatusError as exc:
        raise RecipeParseError(
            f"Recipe page returned HTTP {exc.response.status_code}.",
            reasons=[f"http_{exc.response.status_code}"],
        ) from exc
    except httpx.HTTPError as exc:
        raise RecipeParseError(
            "Could not fetch the recipe page.",
            reasons=["fetch_failed"],
        ) from exc
    finally:
        if owns_client:
            await client.aclose()


def _fmt_time(minutes: int | float | None) -> str | None:
    """Format a duration in minutes as e.g. ``"1 hr 30 min"``; ``None`` if empty."""
    if not minutes or minutes <= 0:
        return None
    total = int(round(minutes))
    hours, mins = divmod(total, 60)
    if hours and mins:
        return f"{hours} hr {mins} min"
    if hours:
        return f"{hours} hr"
    return f"{mins} min"


def _safe(getter) -> object | None:  # noqa: ANN001
    """Call a ``recipe-scrapers`` accessor, swallowing its per-field errors.

    The library raises (rather than returns None) for missing fields, so each
    accessor is guarded individually — a missing yield must not sink the parse.
    """
    try:
        return getter()
    except Exception:  # noqa: BLE001 - library raises many field-specific types
        return None


def parse_with_scrapers(html: str, url: str) -> ParsedRecipe:
    """Parse via ``recipe-scrapers`` (wild mode). Always returns a
    :class:`ParsedRecipe`; completeness is judged by the caller."""
    # supported_only=False = the old "wild mode": try schema.org/JSON-LD on any
    # site, not just the library's explicitly-supported hosts.
    scraper = scrape_html(html, org_url=url, supported_only=False)

    title = _safe(scraper.title) or ""
    raw_ingredients = _safe(scraper.ingredients) or []
    instructions = _safe(scraper.instructions_list)
    if not instructions:
        block = _safe(scraper.instructions)
        instructions = [s for s in str(block or "").split("\n") if s.strip()]

    return ParsedRecipe(
        title=str(title).strip(),
        image_url=_safe(scraper.image),  # type: ignore[arg-type]
        source_url=url,
        recipe_yield=_safe(scraper.yields),  # type: ignore[arg-type]
        prep_time=_fmt_time(_safe(scraper.prep_time)),  # type: ignore[arg-type]
        cook_time=_fmt_time(_safe(scraper.cook_time)),  # type: ignore[arg-type]
        total_time=_fmt_time(_safe(scraper.total_time)),  # type: ignore[arg-type]
        ingredients=[ParsedIngredient(raw=str(line).strip()) for line in raw_ingredients if str(line).strip()],
        instructions=[str(step).strip() for step in instructions if str(step).strip()],
    )


def extract_page_text(html: str) -> str:
    """Strip scripts/styles/nav chrome and return visible text for the LLM.

    Capped at ``_MAX_TEXT_CHARS`` to bound token cost.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template", "svg", "nav", "footer", "header", "form"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    collapsed = "\n".join(line for line in lines if line)
    return collapsed[:_MAX_TEXT_CHARS]


async def scrape_recipe(
    url: str,
    *,
    llm: StructuredLLM | None = None,
    client: httpx.AsyncClient | None = None,
) -> ParsedRecipe:
    """Parse ``url`` into a complete :class:`ParsedRecipe`.

    ``recipe-scrapers`` first; on failure/incompleteness, the LLM fallback if a
    client is wired (T4). Raises :class:`RecipeParseError` (listing what failed)
    when no path yields a complete recipe — including when the fallback is
    unavailable because ``llm`` is ``None``.
    """
    html = await fetch_page(url, client=client)

    scraper_reasons: list[str] = []
    parsed: ParsedRecipe | None = None
    try:
        parsed = parse_with_scrapers(html, url)
    except Exception as exc:  # noqa: BLE001 - library can raise on malformed pages
        logger.info("recipe-scrapers failed for %s: %s", url, exc)
        scraper_reasons.append("scraper_error")

    if parsed is not None and parsed.is_complete():
        return parsed

    if parsed is not None:
        scraper_reasons.extend(f"missing_{m}" for m in parsed.missing())

    # Scraper path insufficient — try the LLM fallback if wired.
    if llm is None:
        raise RecipeParseError(
            "Could not parse this recipe automatically and no LLM fallback is "
            "configured. Try a different source or add it manually.",
            reasons=[*scraper_reasons, "llm_unavailable"],
        )

    page_text = extract_page_text(html)
    if not page_text:
        raise RecipeParseError(
            "The recipe page had no readable text to extract.",
            reasons=[*scraper_reasons, "empty_page_text"],
        )
    return await llm_extract_recipe(llm, page_text=page_text, source_url=url)
