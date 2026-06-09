"""Tests for config persistence behavior."""

from __future__ import annotations

import json
from pathlib import Path

from txt_process.core.config import Config, load_config, save_config


def _read_config_json(config_dir: Path) -> dict[str, object]:
    return json.loads((config_dir / "config.json").read_text(encoding="utf-8"))


def test_save_config_persists_api_key_when_remember_enabled(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("txt_process.core.config.get_config_dir", lambda: tmp_path)
    cfg = Config(remember_api_key=True, api_key="sk-live")

    save_config(cfg)

    payload = _read_config_json(tmp_path)
    assert payload["api_key"] == "sk-live"


def test_save_config_blanks_api_key_when_remember_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("txt_process.core.config.get_config_dir", lambda: tmp_path)
    cfg = Config(remember_api_key=False, api_key="sk-session")

    save_config(cfg)

    payload = _read_config_json(tmp_path)
    assert payload["api_key"] == ""
    assert cfg.api_key == "sk-session"


def test_load_config_blanks_leftover_api_key_when_remember_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("txt_process.core.config.get_config_dir", lambda: tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"remember_api_key": False, "api_key": "leftover", "model": "m"}),
        encoding="utf-8",
    )

    loaded = load_config()

    assert loaded.remember_api_key is False
    assert loaded.api_key == ""


def test_save_and_load_round_trip_without_key_leak(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("txt_process.core.config.get_config_dir", lambda: tmp_path)
    cfg = Config(model="demo", remember_api_key=False, api_key="sk-in-memory")

    save_config(cfg)
    loaded = load_config()

    assert loaded.model == "demo"
    assert loaded.api_key == ""
