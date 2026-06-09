"""Tests for the macOS Python bridge dispatcher."""

from __future__ import annotations

import json
from pathlib import Path

from txt_process.core.config import Config, save_config
from txt_process.macos_bridge.service import dispatch


def _decode(response: str) -> dict[str, object]:
    return json.loads(response)


def test_ping_returns_python_version():
    payload = _decode(dispatch("ping", "{}"))
    assert payload["ok"] is True
    assert payload["result"]["python_version"]


def test_read_settings_redacts_api_key(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("txt_process.core.config.get_config_dir", lambda: tmp_path)
    save_config(Config(remember_api_key=True, api_key="sk-live", model="demo"))

    payload = _decode(dispatch("readSettings", "{}"))

    assert payload["ok"] is True
    assert payload["result"]["model"] == "demo"
    assert payload["result"]["api_key"] == ""


def test_load_document_returns_document_payload(tmp_path: Path):
    source = tmp_path / "story.txt"
    source.write_text("Alice met Bob.", encoding="utf-8")

    payload = _decode(dispatch("loadDocument", json.dumps({"path": str(source)})))

    assert payload["ok"] is True
    assert payload["result"]["kind"] == "txt"
    assert "Alice met Bob." in payload["result"]["text"]


def test_extract_names_emits_progress_events(tmp_path: Path, monkeypatch):
    source = tmp_path / "story.txt"
    source.write_text("Alice met Bob.", encoding="utf-8")
    events: list[str] = []

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            _ = args
            _ = kwargs

        def chat(self, prompt: str, **_kwargs: object) -> str:
            _ = prompt
            return json.dumps({"names": ["Alice"]})

    monkeypatch.setattr("txt_process.core.extraction.LLMClient", FakeClient)
    payload = _decode(
        dispatch(
            "extractNames",
            json.dumps(
                {
                    "documentPath": str(source),
                    "config": {
                        "prompt_template": "{chunk_text}",
                        "request_interval_seconds": 0.0,
                    },
                    "api_key": "ollama",
                }
            ),
            progress_callback=events.append,
            token="token-progress",
        )
    )

    assert payload["ok"] is True
    assert payload["result"]["name_pairs"] == [["Alice", ""]]
    assert any('"type": "progress"' in event for event in events)


def test_cancel_token_short_circuits_extraction(tmp_path: Path, monkeypatch):
    source = tmp_path / "story.txt"
    source.write_text("Alice met Bob.", encoding="utf-8")

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            _ = args
            _ = kwargs

        def chat(self, prompt: str, **_kwargs: object) -> str:
            _ = prompt
            return json.dumps({"names": ["Alice"]})

    monkeypatch.setattr("txt_process.core.extraction.LLMClient", FakeClient)
    _decode(dispatch("cancel", "{}", token="token-cancel"))
    payload = _decode(
        dispatch(
            "extractNames",
            json.dumps(
                {
                    "documentPath": str(source),
                    "config": {
                        "prompt_template": "{chunk_text}",
                        "request_interval_seconds": 0.0,
                    },
                    "api_key": "ollama",
                }
            ),
            token="token-cancel",
        )
    )

    assert payload["ok"] is True
    assert payload["result"]["errors"] == ["cancelled"]


def test_commit_imported_pairs_filters_zero_count_sources(tmp_path: Path):
    source = tmp_path / "story.txt"
    source.write_text("Alice met Bob.", encoding="utf-8")

    payload = _decode(
        dispatch(
            "commitImportedPairs",
            json.dumps(
                {
                    "documentPath": str(source),
                    "pairs": [["Alice", "Alicia"], ["Charlie", "Charles"]],
                }
            ),
        )
    )

    assert payload["ok"] is True
    assert payload["result"]["rows"] == [
        {
            "original_name": "Alice",
            "replacement_name": "Alicia",
            "occurrence_count": 1,
        }
    ]


def test_unknown_method_returns_error():
    payload = _decode(dispatch("nope", "{}"))
    assert payload["ok"] is False
    assert payload["error"] == "pythonRaised"
