"""Persistence helpers for replacement-name cache."""

from __future__ import annotations

import json
from pathlib import Path

from txt_process.core.config import get_config_dir

CACHE_FILE = "name_cache.json"


def get_name_cache_path() -> Path:
    """Return the path of the replacement-name cache file."""
    return get_config_dir() / CACHE_FILE


def normalize_name_list(names: list[str]) -> list[str]:
    """Trim, drop empty values, and dedupe while preserving order."""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in names:
        name = str(raw).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        normalized.append(name)
    return normalized


def load_name_cache() -> list[str]:
    """Load cached replacement names from disk."""
    cache_path = get_name_cache_path()
    if not cache_path.exists():
        return []
    try:
        with open(cache_path, encoding="utf-8") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return []

    if isinstance(payload, dict):
        names = payload.get("names", [])
    elif isinstance(payload, list):
        names = payload
    else:
        names = []

    if not isinstance(names, list):
        return []
    return normalize_name_list([str(item) for item in names])


def save_name_cache(names: list[str]) -> list[str]:
    """Persist replacement names and return normalized stored values."""
    normalized = normalize_name_list(names)
    cache_path = get_name_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump({"names": normalized}, f, indent=2, ensure_ascii=False)
    return normalized


def merge_cached_names(existing: list[str], new_names: list[str]) -> list[str]:
    """Merge current cache with new names, preserving first-seen order."""
    return normalize_name_list([*existing, *new_names])

