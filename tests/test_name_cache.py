"""Tests for replacement-name cache persistence."""

from pathlib import Path

from txt_process.core import name_cache


def test_normalize_name_list_trims_dedupes_and_drops_empty() -> None:
    values = ["  Alice  ", "", "Bob", "Alice", "  ", "Bob", "Carol"]
    assert name_cache.normalize_name_list(values) == ["Alice", "Bob", "Carol"]


def test_merge_cached_names_preserves_first_seen_order() -> None:
    existing = ["Alice", "Bob"]
    new_values = ["Bob", "Carol", "Alice", "Diana"]
    assert name_cache.merge_cached_names(existing, new_values) == [
        "Alice",
        "Bob",
        "Carol",
        "Diana",
    ]


def test_save_then_load_name_cache(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(name_cache, "get_config_dir", lambda: tmp_path)

    stored = name_cache.save_name_cache([" Alice ", "Bob", "Alice", ""])
    assert stored == ["Alice", "Bob"]

    loaded = name_cache.load_name_cache()
    assert loaded == ["Alice", "Bob"]
    assert (tmp_path / "name_cache.json").exists()


def test_load_name_cache_returns_empty_for_invalid_payload(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(name_cache, "get_config_dir", lambda: tmp_path)
    bad_path = tmp_path / "name_cache.json"
    bad_path.write_text("{invalid json", encoding="utf-8")
    assert name_cache.load_name_cache() == []
