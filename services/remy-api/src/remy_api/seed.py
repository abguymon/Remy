"""Default settings seeds loaded from the repo-root YAML files.

New users get their pantry staples from ``pantry.yaml`` (``bypass_staples``) and
their favorite recipe sites from ``recipe_sources.yaml`` (``favorite_sources``
domains). Path resolution walks up from this module to find the repo root; the
files may also be overridden via ``PANTRY_FILE`` / ``RECIPE_SOURCES_FILE`` env
vars (used by the Docker image, where the YAMLs are copied next to the source).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

PANTRY_FILENAME = "pantry.yaml"
RECIPE_SOURCES_FILENAME = "recipe_sources.yaml"


def _find_upwards(filename: str) -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / filename
        if candidate.is_file():
            return candidate
    return None


def _resolve(env_var: str, filename: str) -> Path | None:
    override = os.environ.get(env_var)
    if override:
        path = Path(override)
        return path if path.is_file() else None
    return _find_upwards(filename)


@lru_cache
def default_pantry_items() -> list[str]:
    """Ordered, de-duplicated pantry staples from ``pantry.yaml``."""
    path = _resolve("PANTRY_FILE", PANTRY_FILENAME)
    if path is None:
        return []
    data = yaml.safe_load(path.read_text()) or {}
    items = data.get("bypass_staples") or []
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = str(item).strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


@lru_cache
def default_favorite_sites() -> list[str]:
    """Favorite recipe-site domains from ``recipe_sources.yaml``."""
    path = _resolve("RECIPE_SOURCES_FILE", RECIPE_SOURCES_FILENAME)
    if path is None:
        return []
    data = yaml.safe_load(path.read_text()) or {}
    sources = data.get("favorite_sources") or []
    domains: list[str] = []
    for source in sources:
        domain = (source or {}).get("domain") if isinstance(source, dict) else None
        if domain:
            domains.append(str(domain).strip())
    return domains
