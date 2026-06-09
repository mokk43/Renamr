"""Tests for the public ``txt_process.core.api`` facade."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from txt_process.core import api
from txt_process.core.config import Config
from txt_process.core.document import load_document as load_document_direct
from txt_process.core.extraction import ExtractionResult


def test_load_document_matches_core_loader(tmp_path: Path):
    source = tmp_path / "story.txt"
    source.write_text("Alice met Bob.", encoding="utf-8")

    from_api = api.load_document(source)
    direct = load_document_direct(source)

    assert type(from_api) is type(direct)
    assert from_api.path == direct.path
    assert from_api.text == direct.text


def test_extract_names_delegates_to_core_extraction():
    cfg = Config(prompt_template="{chunk_text}")
    expected = ExtractionResult(name_pairs=[("Alice", "")], counts={"Alice": 1}, errors=[])

    with patch("txt_process.core.api.run_extraction", return_value=expected) as run:
        result = api.extract_names("Alice", cfg, api_key="sk-test")

    run.assert_called_once_with(text="Alice", config=cfg, api_key="sk-test", callbacks=None)
    assert result == expected


def test_replace_and_export_uses_processed_suffix(tmp_path: Path):
    source = tmp_path / "book.txt"
    source.write_text("Alice met Alice.", encoding="utf-8")
    document = api.load_document(source)

    result = api.replace_and_export(document, {"Alice": "Alicia"})

    assert result.output_path == tmp_path / "book_processed.txt"
    assert result.totals == {"Alice": 2}
    assert result.output_path.read_text(encoding="utf-8") == "Alicia met Alicia."


def test_read_and_write_settings_round_trip(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("txt_process.core.config.get_config_dir", lambda: tmp_path)

    config = Config(base_url="https://example.com/v1", model="test-model", remember_api_key=False)
    api.write_settings(config)
    loaded = api.read_settings()

    assert loaded.base_url == "https://example.com/v1"
    assert loaded.model == "test-model"
    assert loaded.api_key == ""
