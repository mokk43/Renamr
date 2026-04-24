"""Name extraction and deduplication logic."""

from __future__ import annotations

import json
import re


def extract_names_from_response(response: str) -> list[str]:
    """
    Extract names from an LLM response.

    Expects strict JSON: ``{"names": ["Name1", "Name2", ...]}``.
    If strict parsing fails, attempts to locate the first matching JSON
    object in wrapping text. No heuristic (line-by-line) fallback is used;
    callers are expected to perform a single corrective retry instead.

    Args:
        response: The LLM response text.

    Returns:
        List of extracted names.

    Raises:
        ValueError: If no valid JSON ``names`` list can be extracted.
    """
    response = response.strip()

    if not response:
        return []

    # Try strict JSON parsing first
    try:
        data = json.loads(response)
        if isinstance(data, dict) and "names" in data:
            names = data["names"]
            if isinstance(names, list):
                return [str(n) for n in names if n]
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the response
    json_match = re.search(r"\{[^{}]*\"names\"\s*:\s*\[[^\]]*\][^{}]*\}", response, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            if isinstance(data, dict) and "names" in data:
                names = data["names"]
                if isinstance(names, list):
                    return [str(n) for n in names if n]
        except json.JSONDecodeError:
            pass

    # Try more aggressive JSON extraction for the bare array form
    array_match = re.search(r"\"names\"\s*:\s*(\[[^\]]*\])", response, re.DOTALL)
    if array_match:
        try:
            names = json.loads(array_match.group(1))
            if isinstance(names, list):
                return [str(n) for n in names if n]
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract names from response: {response[:200]}")


def normalize_name(name: str) -> str:
    """
    Normalize a name for deduplication.

    Currently: strip whitespace.
    Could be extended for full-width/half-width normalization.

    Args:
        name: The name to normalize.

    Returns:
        Normalized name.
    """
    return name.strip()


def dedupe_names(names: list[str]) -> list[str]:
    """
    Deduplicate a list of names while preserving first-seen order.

    Args:
        names: List of names (may contain duplicates).

    Returns:
        Deduplicated list in first-seen order.
    """
    seen: set[str] = set()
    result: list[str] = []

    for name in names:
        normalized = normalize_name(name)

        # Skip empty names
        if not normalized:
            continue

        # Skip duplicates
        if normalized in seen:
            continue

        seen.add(normalized)
        result.append(normalized)

    return result


