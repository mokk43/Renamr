"""Shared fixtures for scenario-level flow tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_epub_io import MINIMAL_CHAPTERS, _build_epub
from txt_process.core.config import Config


@pytest.fixture
def scenario_config() -> Config:
    return Config(
        base_url="http://localhost:11434",
        model="mock-model",
        prompt_template="{chunk_text}",
        request_interval_seconds=0.0,
        begin_scan_chunks=20,
    )


@pytest.fixture
def txt_story_path(tmp_path: Path) -> Path:
    path = tmp_path / "story.txt"
    path.write_text(
        "张三和张三丰在聊天。Alice的故事。Alice met Bob. Alice123 stays.",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def epub_story_path(tmp_path: Path) -> Path:
    return _build_epub(tmp_path / "story.epub", chapters=MINIMAL_CHAPTERS)


@pytest.fixture
def fake_llm_client(monkeypatch):
    def install(names: list[str], *, calls: list[str] | None = None) -> list[str]:
        captured: list[str] = calls if calls is not None else []

        class FakeClient:
            def __init__(self, *args, **kwargs) -> None:
                _ = args
                _ = kwargs

            def chat(self, prompt: str, **_kwargs: object) -> str:
                captured.append(prompt)
                return json.dumps({"names": names}, ensure_ascii=False)

        monkeypatch.setattr("txt_process.core.extraction.LLMClient", FakeClient)
        return captured

    return install
