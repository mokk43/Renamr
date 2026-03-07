"""Name extraction and deduplication logic."""

from __future__ import annotations

import json
import re

# #region agent log
_DEBUG_LOG_PATH = "/Users/gary/git/txt-process/.cursor/debug.log"
def _dbg(loc, msg, data, hyp):
    import time; open(_DEBUG_LOG_PATH, "a").write(json.dumps({"location": loc, "message": msg, "data": data, "hypothesisId": hyp, "timestamp": int(time.time()*1000), "sessionId": "debug-session"}) + "\n")
# #endregion


def extract_names_from_response(response: str) -> list[str]:
    """
    Extract names from an LLM response.

    Expects JSON format: {"names": ["Name1", "Name2", ...]}
    Falls back to extracting JSON from wrapped text if strict parsing fails.

    Args:
        response: The LLM response text.

    Returns:
        List of extracted names.

    Raises:
        ValueError: If no valid names can be extracted.
    """
    response = response.strip()
    # #region agent log
    _dbg("name_extract.py:entry", "extract_names_from_response called", {"response_len": len(response), "response_preview": response[:300] if response else "EMPTY"}, "H1")
    # #endregion

    if not response:
        return []

    # Try strict JSON parsing first
    try:
        data = json.loads(response)
        # #region agent log
        _dbg("name_extract.py:json_ok", "strict JSON parsed", {"data_type": str(type(data)), "has_names": "names" in data if isinstance(data, dict) else False}, "H2")
        # #endregion
        if isinstance(data, dict) and "names" in data:
            names = data["names"]
            if isinstance(names, list):
                return [str(n) for n in names if n]
    except json.JSONDecodeError as e:
        # #region agent log
        _dbg("name_extract.py:json_fail", "strict JSON failed", {"error": str(e)}, "H1")
        # #endregion
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

    # Try more aggressive JSON extraction
    # Look for array pattern
    array_match = re.search(r"\"names\"\s*:\s*(\[[^\]]*\])", response, re.DOTALL)
    if array_match:
        try:
            names = json.loads(array_match.group(1))
            if isinstance(names, list):
                return [str(n) for n in names if n]
        except json.JSONDecodeError:
            pass

    # Try line-by-line extraction as last resort
    # If each line looks like a name (no JSON syntax)
    lines = response.strip().split("\n")
    potential_names = []
    for line in lines:
        line = line.strip()
        # Skip lines that look like JSON or markdown
        if line.startswith(("{", "[", "```", "#", "-", "*")):
            continue
        # Skip empty lines
        if not line:
            continue
        # Skip lines that are too long (probably not names)
        if len(line) > 50:
            continue
        # Remove numbering like "1. " or "- "
        line = re.sub(r"^\d+\.\s*", "", line)
        line = re.sub(r"^[-*]\s*", "", line)
        line = line.strip()
        if line:
            potential_names.append(line)

    if potential_names:
        return potential_names

    # #region agent log
    _dbg("name_extract.py:all_failed", "all parsing methods failed", {"response_preview": response[:200]}, "H1")
    # #endregion
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
