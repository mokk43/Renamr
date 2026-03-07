"""Text chunking for LLM processing."""

from __future__ import annotations

import re

# Default maximum chunk size in bytes (strictly less than this)
DEFAULT_CHUNK_MAX_BYTES = 8 * 1024  # 8KB


def split_into_paragraphs(text: str) -> list[str]:
    """
    Split text into paragraphs.

    A paragraph is a run of non-empty lines separated by one or more blank lines.
    Preserves paragraph internal newlines.

    Args:
        text: The input text.

    Returns:
        List of paragraph strings.
    """
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Split on one or more blank lines (lines with only whitespace count as blank)
    # Pattern matches: newline + optional whitespace + newline (one or more times)
    paragraphs = re.split(r"\n\s*\n+", text)

    # Filter out empty paragraphs and strip leading/trailing whitespace from each
    result = []
    for p in paragraphs:
        stripped = p.strip()
        if stripped:
            result.append(stripped)

    return result


def _byte_length(text: str) -> int:
    """Get the UTF-8 byte length of a string."""
    return len(text.encode("utf-8"))


def _split_oversized_paragraph(paragraph: str, max_bytes: int) -> list[str]:
    """
    Split an oversized paragraph into sub-chunks by UTF-8 bytes.

    Tries to split at sentence boundaries, falling back to character boundaries.

    Args:
        paragraph: The oversized paragraph.
        max_bytes: Maximum bytes per chunk (strict less than).

    Returns:
        List of sub-chunks, each strictly < max_bytes.
    """
    if _byte_length(paragraph) < max_bytes:
        return [paragraph]

    # Try to split at sentence boundaries first
    # Chinese: 。！？；  English: . ! ? ;
    sentence_pattern = r"(?<=[。！？；.!?;])\s*"
    sentences = re.split(sentence_pattern, paragraph)
    sentences = [s for s in sentences if s.strip()]

    chunks: list[str] = []
    current_chunk = ""

    for sentence in sentences:
        test_chunk = current_chunk + sentence if current_chunk else sentence

        if _byte_length(test_chunk) < max_bytes:
            current_chunk = test_chunk
        else:
            # Current chunk is full, save it if non-empty
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""

            # Check if sentence itself is oversized
            if _byte_length(sentence) >= max_bytes:
                # Must split by characters
                sub_chunks = _split_by_bytes(sentence, max_bytes)
                chunks.extend(sub_chunks)
            else:
                current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def _split_by_bytes(text: str, max_bytes: int) -> list[str]:
    """
    Split text by byte length, respecting character boundaries.

    Args:
        text: Text to split.
        max_bytes: Maximum bytes per chunk (strict less than).

    Returns:
        List of chunks, each strictly < max_bytes.
    """
    chunks: list[str] = []
    current_chunk = ""
    current_bytes = 0

    for char in text:
        char_bytes = len(char.encode("utf-8"))

        if current_bytes + char_bytes < max_bytes:
            current_chunk += char
            current_bytes += char_bytes
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = char
            current_bytes = char_bytes

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def split_into_chunks(text: str, max_bytes: int = DEFAULT_CHUNK_MAX_BYTES) -> list[str]:
    """
    Split text into chunks suitable for LLM processing.

    Each chunk is strictly < max_bytes (UTF-8).
    Chunks are built from consecutive paragraphs in order.
    Oversized paragraphs are split by sentence, then by character.

    Args:
        text: The input text.
        max_bytes: Maximum chunk size in bytes (default 16KB).

    Returns:
        List of chunk strings, each strictly < max_bytes UTF-8 bytes.
    """
    if not text.strip():
        return []

    paragraphs = split_into_paragraphs(text)

    if not paragraphs:
        return []

    chunks: list[str] = []
    current_chunk = ""

    for paragraph in paragraphs:
        para_bytes = _byte_length(paragraph)

        # Handle oversized paragraphs
        if para_bytes >= max_bytes:
            # First, save current chunk if non-empty
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""

            # Split the oversized paragraph
            sub_chunks = _split_oversized_paragraph(paragraph, max_bytes)
            chunks.extend(sub_chunks)
            continue

        # Normal paragraph - try to add to current chunk
        # Use double newline as paragraph separator
        separator = "\n\n" if current_chunk else ""
        test_chunk = current_chunk + separator + paragraph

        if _byte_length(test_chunk) < max_bytes:
            current_chunk = test_chunk
        else:
            # Current chunk is full, save it and start new one
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = paragraph

    # Don't forget the last chunk
    if current_chunk:
        chunks.append(current_chunk)

    return chunks
