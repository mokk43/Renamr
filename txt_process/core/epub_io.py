"""EPUB loading and replacement.

Loads an EPUB into a read-only :class:`EpubDocument` (text-only snapshot for
LLM extraction), and writes a processed copy via
:func:`save_epub_with_replacements` which operates on text nodes of every
XHTML/NCX item in the manifest.

Key design choices (see plan):

- The parsed ``EpubBook`` is NOT retained on :class:`EpubDocument`. Every
  save re-reads the source from disk so mutations never leak between runs.
- Extraction scope is *spine items only* (off-spine manifest docs don't
  pollute LLM input). Replacement scope is broader: all ``ITEM_DOCUMENT``
  plus ``ITEM_NAVIGATION`` (NCX) items.
- Adjacent inline text nodes (``<span>``/``<em>``/...) are coalesced before
  replacement so names split by inline wrappers are still matched, guarded
  by tag+attribute equality to avoid destroying styling.
- DOCTYPE is re-prepended manually since BeautifulSoup's ``lxml-xml``
  serialization drops it.
"""

from __future__ import annotations

import warnings
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ebooklib emits ImportWarning / UserWarning on modern Python for the
# TOC / nav rebuild path.  Silence them on import so test output stays
# readable; the warnings are not actionable by end users.
warnings.filterwarnings("ignore", category=ImportWarning, module=r"ebooklib.*")
warnings.filterwarnings("ignore", category=UserWarning, module=r"ebooklib.*")
warnings.filterwarnings("ignore", category=FutureWarning, module=r"ebooklib.*")

from bs4 import BeautifulSoup, Doctype, NavigableString  # noqa: E402
from ebooklib import ITEM_DOCUMENT, epub  # noqa: E402

from txt_process.core.replace import apply_replacements  # noqa: E402

# Inline phrasing tags where adjacent text nodes are safely coalesced for
# matching purposes.  Ruby-related tags are deliberately excluded.
_COALESCE_PARENT_TAGS = frozenset(
    {"span", "em", "i", "b", "strong", "u", "small", "sub", "sup", "mark"}
)

# Block-like tags where crossing from one block to another should introduce
# a separator in extraction text to avoid token concatenation such as
# ``</p><p>`` -> ``AliceBob``.
_TEXT_BREAK_TAGS = frozenset(
    {
        "p",
        "div",
        "section",
        "article",
        "header",
        "footer",
        "aside",
        "blockquote",
        "pre",
        "li",
        "dt",
        "dd",
        "td",
        "th",
        "tr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "title",
    }
)

# Tags whose text content must never be extracted or rewritten.
_EXCLUDE_TAGS = frozenset({"script", "style"})


class EpubError(Exception):
    """Base class for EPUB-related errors."""


class EpubEncryptedError(EpubError):
    """Raised when the EPUB appears to be DRM-protected / font-obfuscated."""


class EpubParseError(EpubError):
    """Raised when the EPUB cannot be parsed as a valid EPUB container."""


class EpubEmptyError(EpubError):
    """Raised when the EPUB has no readable spine content."""


@dataclass(frozen=True)
class EpubDocument:
    """Immutable snapshot of an EPUB's readable text plus display metadata.

    The source :class:`ebooklib.epub.EpubBook` is intentionally NOT retained;
    :func:`save_epub_with_replacements` re-reads the file from disk so a
    second Replace click is never applied on top of already-replaced
    content.
    """

    path: Path
    text: str
    version: str
    chapter_count: int
    size_bytes: int
    display_info: str


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _check_drm(path: Path) -> None:
    """Fail fast for DRM / font-obfuscated EPUBs."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
    except zipfile.BadZipFile as exc:  # pragma: no cover - defensive
        raise EpubParseError(f"Not a valid EPUB zip: {path.name}") from exc
    if "META-INF/encryption.xml" in names:
        raise EpubEncryptedError(
            f"{path.name} is DRM-protected or uses font obfuscation."
        )


def _spine_items(book: epub.EpubBook) -> list[epub.EpubHtml]:
    """Return spine ``ITEM_DOCUMENT`` items in spine order.

    ``book.spine`` is a list of ``(idref, linear)`` tuples; resolve each to
    its manifest item.  Items missing from the manifest are skipped.
    """
    items: list[epub.EpubHtml] = []
    for entry in book.spine:
        # entries are (idref, linear) tuples but a plain idref string is also
        # tolerated by ebooklib.
        idref = entry[0] if isinstance(entry, tuple) else entry
        item = book.get_item_with_id(idref)
        if item is None:
            continue
        if item.get_type() == ITEM_DOCUMENT:
            items.append(item)
    return items


def _extract_visible_text(soup: BeautifulSoup) -> str:
    """Return the visible text of a parsed XHTML soup, in document order."""
    body = soup.find("body") or soup
    parts: list[str] = []
    last_block_id: int | None = None
    for node in body.descendants:
        if isinstance(node, NavigableString) and not isinstance(node, Doctype):
            parent_names = {
                p.name for p in node.parents if getattr(p, "name", None)
            }
            if parent_names & _EXCLUDE_TAGS:
                continue
            text = str(node)
            if text.strip():
                block_parent = next(
                    (
                        p
                        for p in node.parents
                        if getattr(p, "name", None) in _TEXT_BREAK_TAGS
                    ),
                    None,
                )
                block_id = id(block_parent) if block_parent is not None else None
                if parts and block_id != last_block_id:
                    parts.append("\n")
                parts.append(text)
                last_block_id = block_id
    return "".join(parts)


def _parse_xhtml(raw: bytes) -> BeautifulSoup:
    """Parse XHTML/NCX bytes with XML-strict rules."""
    try:
        return BeautifulSoup(raw, "lxml-xml")
    except Exception as exc:  # pragma: no cover - bs4 rarely raises here
        raise EpubParseError(f"Failed to parse XHTML item: {exc}") from exc


def load_epub(path: Path) -> EpubDocument:
    """Load an EPUB and produce a text snapshot suitable for LLM extraction.

    Raises :class:`EpubEncryptedError`, :class:`EpubParseError`, or
    :class:`EpubEmptyError` on failure.
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    _check_drm(path)

    try:
        book = epub.read_epub(str(path), options={"ignore_ncx": False})
    except EpubError:
        raise
    except Exception as exc:
        raise EpubParseError(f"Failed to parse EPUB: {exc}") from exc

    spine = _spine_items(book)
    if not spine:
        raise EpubEmptyError(f"{path.name} has no spine content.")

    sections: list[str] = []
    for item in spine:
        soup = _parse_xhtml(item.get_content())
        text = _extract_visible_text(soup)
        if text.strip():
            sections.append(text)

    full_text = "\n\n".join(sections)
    if not full_text.strip():
        raise EpubEmptyError(f"{path.name} contains no readable text.")

    version = str(getattr(book, "version", "") or "").strip() or "?"
    chapter_count = len(spine)
    size_bytes = path.stat().st_size

    return EpubDocument(
        path=path,
        text=full_text,
        version=version,
        chapter_count=chapter_count,
        size_bytes=size_bytes,
        display_info=_build_display_info(
            path=path,
            size_bytes=size_bytes,
            chapter_count=chapter_count,
            chunk_count=_estimate_chunk_count(full_text),
            version=version,
        ),
    )


def _estimate_chunk_count(text: str) -> int:
    """Compute chunk count once at load so UI never re-runs the chunker."""
    # Imported lazily so that callers which only need loading do not pay for
    # importing the chunker.
    from txt_process.core.chunking import split_into_chunks

    return len(split_into_chunks(text))


def _build_display_info(
    *,
    path: Path,
    size_bytes: int,
    chapter_count: int,
    chunk_count: int,
    version: str,
) -> str:
    size_kb = size_bytes / 1024
    return (
        f"{path.name} | {size_kb:.1f} KB | {chapter_count} chapters | "
        f"{chunk_count} chunks | EPUB v{version}"
    )


# ---------------------------------------------------------------------------
# Saving / replacement
# ---------------------------------------------------------------------------


def _attr_key(element: Any) -> tuple[str, tuple[tuple[str, Any], ...]] | None:
    """Return a hashable signature for an element's tag+attributes.

    Returns ``None`` if the argument is not a tag-like element.
    """
    name = getattr(element, "name", None)
    if not name:
        return None
    attrs = getattr(element, "attrs", {}) or {}
    frozen_attrs = tuple(sorted((k, _freeze(v)) for k, v in attrs.items()))
    return (name, frozen_attrs)


def _freeze(value: Any) -> Any:
    """Convert lists (common for multi-value attrs like ``class``) to tuples."""
    if isinstance(value, list):
        return tuple(value)
    return value


def _is_whitespace_only(node: NavigableString) -> bool:
    return not str(node).strip()


def _are_text_nodes_adjacent(
    prev: NavigableString,
    current: NavigableString,
) -> bool:
    """Return True if ``prev`` and ``current`` are directly adjacent content.

    We allow only whitespace-only text and ``current.parent`` as structural
    traversal steps between the two nodes. This keeps coalescing safe for
    patterns like ``<span>张</span><span>三</span>`` while rejecting
    ``<span>张</span><img/><span>三</span>``.
    """
    cursor = prev.next_element
    while cursor is not None and cursor is not current:
        if isinstance(cursor, NavigableString):
            if _is_whitespace_only(cursor):
                cursor = cursor.next_element
                continue
            return False
        if cursor is current.parent:
            cursor = cursor.next_element
            continue
        return False
    return cursor is current


def _coalesce_runs(
    text_nodes: list[NavigableString],
    coalesce_log: list[str],
) -> list[list[NavigableString]]:
    """Group adjacent text nodes that can safely be coalesced.

    Two nodes are coalesce-mates when:
    - Neither is whitespace-only,
    - Both sit inside a phrasing-inline parent (see ``_COALESCE_PARENT_TAGS``),
    - Their parent elements share both tag name and attribute set,
    - They are adjacent in the document's text-node order.

    When a boundary is rejected, a short human-readable reason is pushed to
    ``coalesce_log``.
    """
    runs: list[list[NavigableString]] = []
    current: list[NavigableString] = []

    def _flush() -> None:
        if len(current) >= 2:
            runs.append(list(current))
        current.clear()

    prev: NavigableString | None = None
    for node in text_nodes:
        if isinstance(node, Doctype):
            _flush()
            prev = None
            continue
        if _is_whitespace_only(node):
            _flush()
            prev = None
            continue

        parent = node.parent
        parent_name = getattr(parent, "name", None)
        if parent_name not in _COALESCE_PARENT_TAGS:
            _flush()
            prev = node
            current = [node]
            continue

        if prev is None:
            current = [node]
        else:
            prev_key = _attr_key(prev.parent)
            this_key = _attr_key(parent)
            is_adjacent = _are_text_nodes_adjacent(prev, node)
            if (
                prev_key == this_key
                and prev_key is not None
                and is_adjacent
            ):
                current.append(node)
            else:
                _flush()
                if prev_key != this_key:
                    coalesce_log.append(
                        f"skipped coalesce: <{parent_name} "
                        f"{_format_attrs(parent)}>"
                    )
                elif not is_adjacent:
                    coalesce_log.append(
                        f"skipped coalesce: non-adjacent text under <{parent_name}>"
                    )
                current = [node]
        prev = node
    _flush()
    return runs


def _format_attrs(element: Any) -> str:
    attrs = getattr(element, "attrs", {}) or {}
    if not attrs:
        return ""
    return " ".join(f"{k}='{_freeze(v)}'" for k, v in attrs.items())


def _collect_target_nodes(
    soup: BeautifulSoup,
    *,
    root_names: tuple[str, ...],
) -> list[NavigableString]:
    """Collect replaceable text nodes under any of ``root_names``.

    Only direct ``NavigableString`` descendants are returned; nodes under
    ``<script>`` / ``<style>`` are filtered out.
    """
    nodes: list[NavigableString] = []
    roots: list[Any] = []
    for name in root_names:
        roots.extend(soup.find_all(name))
    seen: set[int] = set()
    for root in roots:
        for node in root.descendants:
            if not isinstance(node, NavigableString):
                continue
            if isinstance(node, Doctype):
                continue
            parent_names = {
                p.name for p in node.parents if getattr(p, "name", None)
            }
            if parent_names & _EXCLUDE_TAGS:
                continue
            if id(node) in seen:
                continue
            seen.add(id(node))
            nodes.append(node)
    return nodes


def _apply_to_nodes(
    nodes: list[NavigableString],
    mappings: dict[str, str],
    coalesce_log: list[str],
) -> dict[str, int]:
    """Apply ``mappings`` to ``nodes``, returning per-mapping replacement counts.

    Performs adjacent-text-node coalescing in-place when safe: the coalesced
    string is placed on the first node of a run and subsequent nodes in the
    run are cleared.  Counts reflect actual replacements performed.
    """
    counts: dict[str, int] = {}
    if not mappings or not nodes:
        return counts

    runs = _coalesce_runs(nodes, coalesce_log)
    coalesced: set[int] = set()
    for run in runs:
        combined = "".join(str(n) for n in run)
        new_text, delta = apply_replacements(combined, mappings)
        for name, c in delta.items():
            if c > 0:
                counts[name] = counts.get(name, 0) + c
        # Whether or not a run was actually modified, its members must not be
        # re-processed by the per-node fallback below.
        for n in run:
            coalesced.add(id(n))
        if new_text != combined:
            run[0].replace_with(NavigableString(new_text))
            for extra in run[1:]:
                extra.replace_with(NavigableString(""))

    for node in nodes:
        if id(node) in coalesced:
            continue
        text = str(node)
        new_text, delta = apply_replacements(text, mappings)
        for name, c in delta.items():
            if c > 0:
                counts[name] = counts.get(name, 0) + c
        if new_text != text:
            node.replace_with(NavigableString(new_text))
    return counts


_XML_DECL_PREFIX = b"<?xml"


def _extract_doctype(soup: BeautifulSoup) -> bytes:
    """Return the original DOCTYPE as bytes (with a trailing newline) or b''."""
    for node in soup.contents:
        if isinstance(node, Doctype):
            return f"<!DOCTYPE {node}>\n".encode()
    return b""


def _serialize_soup(soup: BeautifulSoup) -> bytes:
    """Serialize a soup preserving XML declaration and DOCTYPE order.

    BeautifulSoup's ``lxml-xml`` parser drops the DOCTYPE during output; we
    capture it separately and splice it in between the XML declaration and
    the root element so the result is:

        <?xml version="1.0" encoding="utf-8"?>
        <!DOCTYPE html>
        <html ...>
    """
    doctype = _extract_doctype(soup)
    # Drop Doctype from contents before serialization so it isn't emitted
    # twice if bs4 decides to include it.
    for node in list(soup.contents):
        if isinstance(node, Doctype):
            node.extract()
    body = str(soup).encode("utf-8")
    if not doctype:
        return body
    # Insert the DOCTYPE line after the XML declaration (if present) so the
    # output follows conventional XML ordering.
    if body.startswith(_XML_DECL_PREFIX):
        end = body.find(b"?>")
        if end != -1:
            end += 2  # include the closing '?>'
            # Skip an optional trailing newline so we don't double-space.
            tail = body[end:]
            if tail.startswith(b"\n"):
                tail = tail[1:]
            return body[:end] + b"\n" + doctype + tail
    return doctype + body


# Media types that identify rewrite candidates inside the EPUB zip.
_XHTML_MEDIA_TYPES = frozenset(
    {"application/xhtml+xml", "text/html"}
)
_NCX_MEDIA_TYPES = frozenset({"application/x-dtbncx+xml"})
_OPF_MEDIA_TYPES = frozenset({"application/oebps-package+xml"})

# File extensions used as a fallback when the OPF manifest is unavailable.
_XHTML_EXTS = frozenset({".xhtml", ".html", ".htm"})
_NCX_EXTS = frozenset({".ncx"})
_OPF_EXTS = frozenset({".opf"})


def _classify_zip_entry(
    name: str,
    manifest: dict[str, str],
) -> str | None:
    """Return one of ``"xhtml"``, ``"ncx"``, ``"opf"`` or ``None``.

    Uses OPF-declared media types when available; falls back to the file
    extension otherwise.
    """
    media = manifest.get(name, "").lower()
    if media in _XHTML_MEDIA_TYPES:
        return "xhtml"
    if media in _NCX_MEDIA_TYPES:
        return "ncx"
    if media in _OPF_MEDIA_TYPES:
        return "opf"
    ext = Path(name).suffix.lower()
    if ext in _XHTML_EXTS:
        return "xhtml"
    if ext in _NCX_EXTS:
        return "ncx"
    if ext in _OPF_EXTS:
        return "opf"
    return None


def _read_manifest(zf: zipfile.ZipFile) -> dict[str, str]:
    """Map ``zip_member_name -> media_type`` by parsing all ``.opf`` files.

    We parse any OPF encountered (there's usually exactly one); a package's
    ``<manifest>/<item>`` entries declare ``href`` and ``media-type``.
    """
    manifest: dict[str, str] = {}
    for info in zf.infolist():
        if not info.filename.lower().endswith(".opf"):
            continue
        try:
            soup = BeautifulSoup(zf.read(info.filename), "lxml-xml")
        except Exception:
            continue
        opf_dir = str(Path(info.filename).parent)
        for item in soup.find_all("item"):
            href = item.get("href")
            media_type = (item.get("media-type") or "").lower()
            if not href:
                continue
            # Resolve href relative to OPF location.
            full = f"{opf_dir}/{href}" if opf_dir and opf_dir != "." else href
            # Normalize away any "./" segments.
            full = str(Path(full)).replace("\\", "/")
            manifest[full] = media_type
    return manifest


def _apply_to_xhtml_bytes(
    raw: bytes,
    mappings: dict[str, str],
    *,
    root_names: tuple[str, ...],
    coalesce_log: list[str],
) -> tuple[bytes, dict[str, int]]:
    """Apply replacements to the XHTML/NCX bytes, returning (new_bytes, counts).

    If no replacements occur, the input bytes are returned unchanged.
    """
    if not raw:
        return raw, {}
    soup = _parse_xhtml(raw)
    nodes = _collect_target_nodes(soup, root_names=root_names)
    counts = _apply_to_nodes(nodes, mappings, coalesce_log)
    if not any(counts.values()):
        return raw, counts
    return _serialize_soup(soup), counts


def save_epub_with_replacements(
    doc: EpubDocument,
    mappings: dict[str, str],
    output_path: Path,
) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    """Apply name replacements and write a new EPUB to ``output_path``.

    Implementation note: we bypass :func:`ebooklib.epub.write_epub` because
    that writer regenerates ``<head>``/``<title>``, the EPUB 3 ``nav.xhtml``,
    and EPUB 2 ``toc.ncx`` from scratch using :attr:`EpubBook.toc` and
    :attr:`EpubBook.title`, discarding any in-place edits to the raw content
    bytes.  Writing the zip directly preserves the source structure exactly
    and guarantees that replacements survive round-trip.

    Returns ``(totals, per_item)``.
    """
    if not doc.path.exists():
        raise FileNotFoundError(f"File not found: {doc.path}")

    totals: dict[str, int] = {}
    per_item: dict[str, dict[str, int]] = {}
    coalesce_log: list[str] = []

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(doc.path, "r") as zin, zipfile.ZipFile(
            output_path, "w", zipfile.ZIP_DEFLATED
        ) as zout:
            manifest = _read_manifest(zin)
            # The EPUB spec requires the `mimetype` entry to be the first
            # file and stored uncompressed; pass it through verbatim.
            for info in zin.infolist():
                if info.filename == "mimetype":
                    zout.writestr(
                        info, zin.read(info.filename), compress_type=zipfile.ZIP_STORED
                    )
                    break
            for info in zin.infolist():
                if info.filename == "mimetype":
                    continue
                raw = zin.read(info.filename)
                kind = _classify_zip_entry(info.filename, manifest)
                if kind == "xhtml":
                    new_bytes, counts = _apply_to_xhtml_bytes(
                        raw,
                        mappings,
                        root_names=("body", "title"),
                        coalesce_log=coalesce_log,
                    )
                    if any(counts.values()):
                        per_item[info.filename] = counts
                        for name, c in counts.items():
                            if c > 0:
                                totals[name] = totals.get(name, 0) + c
                    zout.writestr(info, new_bytes, compress_type=zipfile.ZIP_DEFLATED)
                elif kind == "ncx":
                    new_bytes, counts = _apply_to_xhtml_bytes(
                        raw,
                        mappings,
                        root_names=(
                            "navMap",
                            "pageList",
                            "navList",
                            "docTitle",
                            "docAuthor",
                        ),
                        coalesce_log=coalesce_log,
                    )
                    if any(counts.values()):
                        per_item[info.filename] = counts
                        for name, c in counts.items():
                            if c > 0:
                                totals[name] = totals.get(name, 0) + c
                    zout.writestr(info, new_bytes, compress_type=zipfile.ZIP_DEFLATED)
                else:
                    # OPF and everything else pass through unchanged.
                    zout.writestr(info, raw, compress_type=zipfile.ZIP_DEFLATED)
    except zipfile.BadZipFile as exc:
        raise EpubParseError(f"Failed to parse EPUB: {exc}") from exc

    return totals, per_item
