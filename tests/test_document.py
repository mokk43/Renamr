"""Tests for the Document abstraction."""

from __future__ import annotations

from pathlib import Path

from txt_process.core.document import (
    EpubDocument,
    TextDocument,
    load_document,
)


def test_load_document_dispatches_by_suffix_for_txt(tmp_path: Path):
    path = tmp_path / "sample.txt"
    path.write_text("Alice and Bob.", encoding="utf-8")
    doc = load_document(path)
    assert isinstance(doc, TextDocument)
    assert doc.kind == "txt"
    assert doc.supports_normalize is True
    assert doc.encoding == "utf-8"
    assert "Alice" in doc.text


def test_load_document_dispatches_by_suffix_case_insensitive(tmp_path: Path):
    path = tmp_path / "sample.TXT"
    path.write_text("x", encoding="utf-8")
    doc = load_document(path)
    assert isinstance(doc, TextDocument)


def test_text_document_save_processed_matches_legacy(tmp_path: Path):
    """Regression: TextDocument.save_processed behaves like old txt flow."""
    path = tmp_path / "story.txt"
    path.write_text("Alice met Bob. Alice smiled.", encoding="utf-8")
    doc = load_document(path)
    assert isinstance(doc, TextDocument)

    out = tmp_path / "story_processed.txt"
    totals, per_item = doc.save_processed({"Alice": "Anna"}, out)

    assert per_item is None
    assert totals.get("Alice") == 2
    assert out.read_text(encoding="utf-8") == "Anna met Bob. Anna smiled."


def test_load_document_epub_kind(tmp_path: Path):
    # Use the epub fixture builder locally to avoid circular test deps.
    from tests.test_epub_io import MINIMAL_CHAPTERS, _build_epub

    epub_path = _build_epub(tmp_path / "book.epub", chapters=MINIMAL_CHAPTERS)
    doc = load_document(epub_path)
    assert isinstance(doc, EpubDocument)
    assert doc.kind == "epub"
    assert doc.supports_normalize is False
    assert doc.encoding is None
    assert "张三" in doc.text
