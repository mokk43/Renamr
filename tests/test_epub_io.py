"""Tests for EPUB I/O and replacement."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from ebooklib import epub
from lxml import etree

from txt_process.core.epub_io import (
    EpubEmptyError,
    EpubEncryptedError,
    EpubParseError,
    load_epub,
    save_epub_with_replacements,
)

# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------

MINIMAL_CHAPTERS: list[tuple[str, str, str]] = [
    (
        "ch1",
        "第一章",
        "<h1>第一章</h1><p>张三走进了房间。他看到李四正在看书。</p>"
        "<p>\"你好，李四，\"张三说道。</p>",
    ),
    (
        "ch2",
        "第二章",
        "<h1>第二章</h1><p>张三丰是另一个角色。</p>"
        "<p>王五和赵六也来了。</p>",
    ),
]

ADVERSARIAL_CHAPTERS: list[tuple[str, str, str]] = [
    (
        "ch1",
        "张三的故事",  # title with target name
        (
            "<h1>张三的故事</h1>"
            "<p>普通段落：张三走进房间。</p>"
            "<p>分裂名：<span>张</span><span>三</span>写了一封信。</p>"
            "<p>长度保护：张三丰是另一个角色。</p>"
            "<p>带样式分裂：<span class='red'>张</span><span>三</span>坐下。</p>"
            "<p>不可变样式块：见下。</p>"
            "<style>.foo::before { content: '张三'; }</style>"
            "<script>var s = '张三';</script>"
        ),
    ),
]


def _build_epub(
    path: Path,
    *,
    chapters: list[tuple[str, str, str]],
    include_css: bool = True,
    include_image: bool = True,
    toc_title: str = "张三的书",
) -> Path:
    book = epub.EpubBook()
    book.set_identifier("renamr-test-id")
    book.set_title(toc_title)
    book.set_language("zh")
    book.add_author("测试")

    html_items: list[epub.EpubHtml] = []
    for ch_id, ch_title, ch_body in chapters:
        html = epub.EpubHtml(
            title=ch_title,
            file_name=f"{ch_id}.xhtml",
            lang="zh",
        )
        html.content = (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<!DOCTYPE html>\n'
            f'<html xmlns="http://www.w3.org/1999/xhtml">'
            f"<head><title>{ch_title}</title></head>"
            f"<body>{ch_body}</body></html>"
        ).encode()
        book.add_item(html)
        html_items.append(html)

    if include_css:
        css = epub.EpubItem(
            uid="style",
            file_name="style/main.css",
            media_type="text/css",
            content="body { font-family: serif; } /* 张三 */".encode(),
        )
        book.add_item(css)

    if include_image:
        # Tiny valid 1x1 PNG
        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000d49444154789c63600100000500010d0a2db40000000049454e44ae426082"
        )
        img = epub.EpubItem(
            uid="cover-img",
            file_name="images/cover.png",
            media_type="image/png",
            content=png,
        )
        book.add_item(img)

    book.toc = tuple(html_items)
    book.spine = ["nav", *html_items]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    epub.write_epub(str(path), book)
    return path


@pytest.fixture
def minimal_epub(tmp_path: Path) -> Path:
    return _build_epub(tmp_path / "minimal.epub", chapters=MINIMAL_CHAPTERS)


@pytest.fixture
def adversarial_epub(tmp_path: Path) -> Path:
    return _build_epub(tmp_path / "adversarial.epub", chapters=ADVERSARIAL_CHAPTERS)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


class TestLoadEpub:
    def test_load_extracts_body_text(self, minimal_epub: Path):
        doc = load_epub(minimal_epub)
        assert "张三" in doc.text
        assert "李四" in doc.text
        assert "张三丰" in doc.text
        assert doc.chapter_count >= 2
        assert doc.size_bytes == minimal_epub.stat().st_size

    def test_display_info_contains_key_fields(self, minimal_epub: Path):
        doc = load_epub(minimal_epub)
        assert minimal_epub.name in doc.display_info
        assert "chapters" in doc.display_info
        assert "chunks" in doc.display_info
        assert "EPUB v" in doc.display_info

    def test_extraction_preserves_block_separators(self, tmp_path: Path):
        epub_path = _build_epub(
            tmp_path / "separators.epub",
            chapters=[("ch1", "t", "<h1>Alice</h1><p>Bob</p>")],
            toc_title="book",
        )
        doc = load_epub(epub_path)
        assert "AliceBob" not in doc.text
        assert "Alice" in doc.text and "Bob" in doc.text

    def test_excludes_script_and_style(self, adversarial_epub: Path):
        doc = load_epub(adversarial_epub)
        # Style/script blocks contain `张三` but its inclusion in body text
        # should come only from visible paragraphs (not from style/script
        # themselves).  We can't assert absence of the substring because it
        # also appears in visible text; instead, assert the style/script
        # strings themselves don't appear.
        assert "content:" not in doc.text
        assert "var s" not in doc.text

    def test_drm_detected(self, tmp_path: Path, minimal_epub: Path):
        drm_path = tmp_path / "drm.epub"
        # Re-pack the existing epub but inject a META-INF/encryption.xml.
        with zipfile.ZipFile(minimal_epub) as src, zipfile.ZipFile(
            drm_path, "w", zipfile.ZIP_DEFLATED
        ) as dst:
            for info in src.infolist():
                dst.writestr(info, src.read(info.filename))
            dst.writestr("META-INF/encryption.xml", "<encryption/>")
        with pytest.raises(EpubEncryptedError):
            load_epub(drm_path)

    def test_corrupt_file_raises_parse_error(self, tmp_path: Path):
        bad = tmp_path / "broken.epub"
        bad.write_bytes(b"not a zip at all")
        with pytest.raises((EpubParseError, EpubEncryptedError)):
            # Either typed error is acceptable; both indicate rejection.
            load_epub(bad)

    def test_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_epub(tmp_path / "missing.epub")

    def test_empty_spine_raises(self, tmp_path: Path):
        # Construct a minimal valid EPUB with only nav (no content chapters).
        book = epub.EpubBook()
        book.set_identifier("empty")
        book.set_title("empty")
        book.set_language("en")
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = []
        out = tmp_path / "empty.epub"
        epub.write_epub(str(out), book)
        with pytest.raises(EpubEmptyError):
            load_epub(out)


# ---------------------------------------------------------------------------
# Replacement
# ---------------------------------------------------------------------------


def _read_xhtml_bodies(path: Path) -> dict[str, str]:
    """Return ``{zip_member: raw_xhtml}`` for every XHTML item in ``path``.

    Reads directly from the zip so we see the bytes our writer produced
    rather than ebooklib's post-regenerated ``get_content`` output.
    """
    out: dict[str, str] = {}
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name.lower().endswith((".xhtml", ".html", ".htm")):
                out[name] = zf.read(name).decode("utf-8")
    return out


def _read_ncx(path: Path) -> str | None:
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name.lower().endswith(".ncx"):
                return zf.read(name).decode("utf-8")
    return None


class TestSaveReplacement:
    def test_body_text_replaced(
        self, minimal_epub: Path, tmp_path: Path
    ):
        doc = load_epub(minimal_epub)
        out = tmp_path / "out.epub"
        totals, per_item = save_epub_with_replacements(
            doc, {"张三": "李明", "李四": "王二"}, out
        )
        assert totals.get("张三", 0) >= 2
        assert totals.get("李四", 0) >= 2
        bodies = _read_xhtml_bodies(out)
        joined = "\n".join(bodies.values())
        assert "李明" in joined
        assert "王二" in joined

    def test_length_desc_overlap_safety(
        self, minimal_epub: Path, tmp_path: Path
    ):
        """When both names are mapped, the longer one wins (no `李明丰`)."""
        doc = load_epub(minimal_epub)
        out = tmp_path / "out.epub"
        save_epub_with_replacements(
            doc,
            {"张三": "李明", "张三丰": "无忌爷爷"},
            out,
        )
        bodies = _read_xhtml_bodies(out)
        joined = "\n".join(bodies.values())
        assert "无忌爷爷" in joined
        assert "李明丰" not in joined

    def test_per_item_keys_are_file_names(
        self, minimal_epub: Path, tmp_path: Path
    ):
        doc = load_epub(minimal_epub)
        totals, per_item = save_epub_with_replacements(
            doc, {"张三": "李明"}, tmp_path / "out.epub"
        )
        assert all("/" in k or k.endswith(".xhtml") for k in per_item)

    def test_style_script_not_modified(
        self, adversarial_epub: Path, tmp_path: Path
    ):
        doc = load_epub(adversarial_epub)
        out = tmp_path / "out.epub"
        save_epub_with_replacements(doc, {"张三": "李明"}, out)
        bodies = _read_xhtml_bodies(out)
        joined = "\n".join(bodies.values())
        # The 张三 inside <style> / <script> must be preserved verbatim.
        assert "content: '张三'" in joined
        assert "var s = '张三'" in joined

    def test_coalescing_matches_split_nodes(
        self, adversarial_epub: Path, tmp_path: Path
    ):
        doc = load_epub(adversarial_epub)
        out = tmp_path / "out.epub"
        totals, _ = save_epub_with_replacements(
            doc,
            {"张三": "李明", "张三丰": "无忌爷爷"},
            out,
        )
        bodies = _read_xhtml_bodies(out)
        # Parse each body and extract visible text so we can assert across
        # coalesced span boundaries.
        from bs4 import BeautifulSoup

        texts = [
            BeautifulSoup(raw, "lxml-xml").get_text()
            for raw in bodies.values()
        ]
        joined_text = "\n".join(texts)
        # The split `<span>张</span><span>三</span>` run should now
        # contain `李明` in its coalesced slot.
        assert "李明写了一封信" in joined_text
        # `张三丰` is explicitly preserved via longer-name mapping.
        assert "无忌爷爷是另一个角色" in joined_text
        # Totals should include at least the 3+ visible occurrences of
        # plain "张三" across the file (coalesced split + title + paragraph).
        assert totals.get("张三", 0) >= 3

    def test_non_adjacent_inline_nodes_are_not_coalesced(self, tmp_path: Path):
        epub_path = _build_epub(
            tmp_path / "non_adjacent.epub",
            chapters=[
                (
                    "ch1",
                    "章节",
                    "<p><span>张</span><img src='x.png'/><span>三</span></p>",
                )
            ],
            toc_title="book",
        )
        doc = load_epub(epub_path)
        out = tmp_path / "out.epub"
        totals, _ = save_epub_with_replacements(doc, {"张三": "李明"}, out)
        assert totals.get("张三", 0) == 0
        bodies = _read_xhtml_bodies(out)
        joined = "\n".join(bodies.values())
        assert "李明" not in joined

    def test_title_replaced(
        self, adversarial_epub: Path, tmp_path: Path
    ):
        doc = load_epub(adversarial_epub)
        out = tmp_path / "out.epub"
        save_epub_with_replacements(doc, {"张三": "李明"}, out)
        bodies = _read_xhtml_bodies(out)
        joined = "\n".join(bodies.values())
        assert "<title>李明的故事</title>" in joined

    def test_ncx_replaced(self, minimal_epub: Path, tmp_path: Path):
        doc = load_epub(minimal_epub)
        out = tmp_path / "out.epub"
        save_epub_with_replacements(doc, {"张三的书": "李明的书"}, out)
        ncx = _read_ncx(out)
        assert ncx is not None
        assert "李明的书" in ncx

    def test_round_trip_integrity(
        self, minimal_epub: Path, tmp_path: Path
    ):
        original = epub.read_epub(str(minimal_epub))
        original_ids = sorted(i.id for i in original.get_items())
        css_item = next(
            (i for i in original.get_items() if i.file_name.endswith(".css")),
            None,
        )
        img_item = next(
            (i for i in original.get_items() if i.file_name.endswith(".png")),
            None,
        )
        assert css_item is not None and img_item is not None

        doc = load_epub(minimal_epub)
        out = tmp_path / "out.epub"
        save_epub_with_replacements(doc, {"张三": "李明"}, out)

        reloaded = epub.read_epub(str(out))
        new_ids = sorted(i.id for i in reloaded.get_items())
        assert new_ids == original_ids

        new_css = next(
            i for i in reloaded.get_items() if i.file_name.endswith(".css")
        )
        new_img = next(
            i for i in reloaded.get_items() if i.file_name.endswith(".png")
        )
        assert new_css.get_content() == css_item.get_content()
        assert new_img.get_content() == img_item.get_content()

    def test_xml_well_formedness(
        self, adversarial_epub: Path, tmp_path: Path
    ):
        doc = load_epub(adversarial_epub)
        out = tmp_path / "out.epub"
        save_epub_with_replacements(doc, {"张三": "李明"}, out)
        bodies = _read_xhtml_bodies(out)
        for name, raw in bodies.items():
            # Should parse without errors.
            try:
                etree.fromstring(raw.encode("utf-8"))
            except etree.XMLSyntaxError as exc:
                pytest.fail(f"{name} is not well-formed XML: {exc}")

    def test_idempotence_via_reread(
        self, minimal_epub: Path, tmp_path: Path
    ):
        """Calling save twice with different mappings uses pristine source."""
        doc = load_epub(minimal_epub)
        out_a = tmp_path / "a.epub"
        out_b = tmp_path / "b.epub"

        totals_a, _ = save_epub_with_replacements(doc, {"张三": "李明"}, out_a)
        totals_b, _ = save_epub_with_replacements(doc, {"李四": "王二"}, out_b)

        # totals_a only counts 张三, totals_b only counts 李四 — they must not
        # share entries.
        assert "李四" not in totals_a
        assert "张三" not in totals_b

        bodies_b = _read_xhtml_bodies(out_b)
        joined_b = "\n".join(bodies_b.values())
        # 张三 remains in out_b because only 李四 was mapped.
        assert "张三" in joined_b
        assert "李明" not in joined_b
        assert "王二" in joined_b

    def test_totals_match_actual_replacements(
        self, minimal_epub: Path, tmp_path: Path
    ):
        doc = load_epub(minimal_epub)
        out = tmp_path / "out.epub"
        totals, per_item = save_epub_with_replacements(
            doc, {"张三": "李明"}, out
        )
        # Count 李明 occurrences in every XHTML + NCX item in the output.
        with zipfile.ZipFile(out) as zf:
            rewritten_bytes = b"".join(
                zf.read(name)
                for name in zf.namelist()
                if name.lower().endswith((".xhtml", ".ncx", ".html", ".htm"))
            )
        rewritten = rewritten_bytes.decode("utf-8")
        assert rewritten.count("李明") == totals["张三"]
        # Per-item totals sum to global total.
        per_item_sum = sum(
            c for counts in per_item.values() for c in counts.values()
        )
        assert per_item_sum == totals["张三"]
