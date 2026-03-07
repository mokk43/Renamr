"""File I/O with encoding detection."""

from __future__ import annotations

from pathlib import Path

import charset_normalizer


def load_text_file(path: Path) -> tuple[str, str]:
    """
    Load a text file with automatic encoding detection.

    Args:
        path: Path to the text file.

    Returns:
        Tuple of (text_content, detected_encoding).

    Raises:
        FileNotFoundError: If file does not exist.
        PermissionError: If file cannot be read.
        ValueError: If encoding cannot be detected.
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    # Read raw bytes
    raw_bytes = path.read_bytes()

    # Check for BOM markers first
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return raw_bytes[3:].decode("utf-8"), "utf-8-sig"
    if raw_bytes.startswith(b"\xff\xfe"):
        return raw_bytes[2:].decode("utf-16-le"), "utf-16-le"
    if raw_bytes.startswith(b"\xfe\xff"):
        return raw_bytes[2:].decode("utf-16-be"), "utf-16-be"

    # Try common encodings in order of preference
    encodings_to_try = ["utf-8", "gb18030", "gbk", "big5", "shift_jis", "euc-kr"]

    for encoding in encodings_to_try:
        try:
            text = raw_bytes.decode(encoding)
            return text, encoding
        except (UnicodeDecodeError, LookupError):
            continue

    # Fall back to charset_normalizer for detection
    result = charset_normalizer.from_bytes(raw_bytes).best()
    if result is not None:
        encoding = result.encoding
        text = str(result)
        return text, encoding

    raise ValueError(f"Could not detect encoding for file: {path}")


def save_text_file(path: Path, content: str, encoding: str = "utf-8") -> None:
    """
    Save text content to a file.

    Args:
        path: Path to save to.
        content: Text content to save.
        encoding: Encoding to use (default utf-8).

    Raises:
        PermissionError: If file cannot be written.
        OSError: If write fails.
    """
    # Normalize encoding name for writing
    write_encoding = encoding
    if encoding == "utf-8-sig":
        write_encoding = "utf-8-sig"
    elif encoding in ("utf-16-le", "utf-16-be"):
        write_encoding = encoding
    else:
        # Default to utf-8 for output
        write_encoding = "utf-8"

    path.write_text(content, encoding=write_encoding)
