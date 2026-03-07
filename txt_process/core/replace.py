"""Text replacement logic."""

from __future__ import annotations

from pathlib import Path


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

    # Sort by original name length descending to handle overlaps
    sorted_originals = sorted(mappings.keys(), key=len, reverse=True)

    counts: dict[str, int] = {}
    result = text

    for original in sorted_originals:
        replacement = mappings[original]
        count = result.count(original)
        counts[original] = count

        if count > 0:
            result = result.replace(original, replacement)

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
