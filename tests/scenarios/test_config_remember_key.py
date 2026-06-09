"""Scenario checks for remember-api-key persistence policy."""

from __future__ import annotations

from pathlib import Path

from txt_process.core.api import read_settings, write_settings
from txt_process.core.config import Config


def test_config_round_trip_honors_remember_api_key(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("txt_process.core.config.get_config_dir", lambda: tmp_path)

    remembered = Config(model="demo", remember_api_key=True, api_key="sk-remembered")
    write_settings(remembered)
    loaded = read_settings()
    assert loaded.api_key == "sk-remembered"

    session_only = Config(model="demo", remember_api_key=False, api_key="sk-session")
    write_settings(session_only)
    loaded = read_settings()
    assert loaded.api_key == ""
