"""Text replacement logic."""

from __future__ import annotations

import re
from pathlib import Path


def _contains_ascii_letters(value: str) -> bool:
    """Return True when ``value`` includes at least one English letter."""
    return bool(re.search(r"[A-Za-z]", value))


def _build_name_pattern(original: str) -> re.Pattern[str]:
    """Build a compiled regex for *original* with safe word boundaries.

    For names containing ASCII letters the pattern is wrapped with negative
    lookaround for adjacent ASCII letters so that e.g. "terran" does **not**
    match inside "terrain".  Standard ``\\b`` is unsuitable because Python 3
    treats CJK characters as ``\\w``, which would prevent matches adjacent to
    Chinese text (e.g. "这是terran的故事").

    Non-ASCII-only names get a plain escaped pattern (no boundary guards).
    """
    escaped = re.escape(original)
    if _contains_ascii_letters(original):
        return re.compile(
            rf"(?<![A-Za-z]){escaped}(?![A-Za-z])",
            flags=re.IGNORECASE,
        )
    return re.compile(escaped)


def count_name_occurrences(text: str, original: str) -> int:
    """Count how many times *original* appears in *text*.

    Uses the same boundary-aware logic as replacement so the UI count
    matches what ``apply_replacements`` would actually substitute.
    """
    if not original or not text:
        return 0
    pattern = _build_name_pattern(original)
    return len(pattern.findall(text))


def apply_replacements(text: str, mappings: dict[str, str]) -> tuple[str, dict[str, int]]:
    """
    Apply name replacements to text.

    Replaces original names with their replacements in descending length order
    to avoid overlap issues (e.g., "张三丰" before "张三").

    Args:
        text: The original text.
        mappings: Dict of original_name -> replacement_name.

    Returns:
        Tuple of (result_text, counts_dict) where counts_dict maps
        original_name -> number of replacements made.
    """
    if not mappings:
        return text, {}

    sorted_originals = sorted(mappings.keys(), key=len, reverse=True)

    counts: dict[str, int] = {}
    result = text

    for original in sorted_originals:
        replacement = mappings[original]
        pattern = _build_name_pattern(original)
        result, count = pattern.subn(lambda _, rep=replacement: rep, result)
        counts[original] = count

    return result, counts


def build_output_path(input_path: Path) -> Path:
    """
    Build the output file path with _processed suffix.

    Inserts '_processed' before the file extension.
    Examples:
        story.txt -> story_processed.txt
        story -> story_processed

    Args:
        input_path: Path to the input file.

    Returns:
        Path for the output file.
    """
    stem = input_path.stem
    suffix = input_path.suffix

    new_name = f"{stem}_processed{suffix}"
    return input_path.parent / new_name
