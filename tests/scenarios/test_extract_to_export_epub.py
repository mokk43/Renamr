"""Scenario tests for EPUB flows through ``core.api``."""

from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from txt_process.core import api
from txt_process.core.document import EpubDocument
from txt_process.core.epub_io import EpubEncryptedError


def test_epub_extract_to_export_flow(
    epub_story_path: Path,
    scenario_config,
    fake_llm_client,
    tmp_path: Path,
):
    document = api.load_document(epub_story_path)
    assert isinstance(document, EpubDocument)

    llm_calls = fake_llm_client(["张三", "李四"])
    with patch("txt_process.core.extraction.split_into_chunks", return_value=[document.text]):
        extraction = api.extract_names(document.text, scenario_config, api_key="ollama")

    assert llm_calls == [document.text]
    assert [name for name, _ in extraction.name_pairs] == ["张三", "李四"]

    output_path = tmp_path / "story_processed.epub"
    replace_result = api.replace_and_export(
        document,
        {"张三": "李明", "李四": "王二"},
        output_path=output_path,
    )
    assert replace_result.output_path == output_path
    assert output_path.exists()

    with zipfile.ZipFile(epub_story_path) as original_zip, zipfile.ZipFile(output_path) as new_zip:
        original_css = next(name for name in original_zip.namelist() if name.endswith("main.css"))
        new_css = next(name for name in new_zip.namelist() if name.endswith("main.css"))
        original_png = next(name for name in original_zip.namelist() if name.endswith("cover.png"))
        new_png = next(name for name in new_zip.namelist() if name.endswith("cover.png"))
        assert original_zip.read(original_css) == new_zip.read(new_css)
        assert original_zip.read(original_png) == new_zip.read(new_png)

        xhtml_entries = [name for name in new_zip.namelist() if name.endswith(".xhtml")]
        xhtml_text = "\n".join(new_zip.read(name).decode("utf-8") for name in xhtml_entries)
        assert "李明" in xhtml_text
        assert "王二" in xhtml_text

        ncx_entry = next(name for name in new_zip.namelist() if name.endswith(".ncx"))
        ncx_text = new_zip.read(ncx_entry).decode("utf-8")
        assert "李明的书" in ncx_text


def test_epub_encryption_is_rejected_before_extraction(
    epub_story_path: Path,
    tmp_path: Path,
):
    drm_path = tmp_path / "encrypted.epub"
    with (
        zipfile.ZipFile(epub_story_path) as source,
        zipfile.ZipFile(drm_path, "w", zipfile.ZIP_DEFLATED) as dest,
    ):
        for info in source.infolist():
            dest.writestr(info, source.read(info.filename))
        dest.writestr("META-INF/encryption.xml", "<encryption/>")

    with pytest.raises(EpubEncryptedError):
        api.load_document(drm_path)
