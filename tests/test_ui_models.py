"""Tests for Qt table models."""

import pytest

try:
    from PySide6.QtCore import Qt

    from txt_process.ui.models import NameTableModel

    HAS_PYSIDE6 = True
except ModuleNotFoundError:
    HAS_PYSIDE6 = False

pytestmark = pytest.mark.skipif(not HAS_PYSIDE6, reason="PySide6 is not installed")


class TestNameTableModel:
    """Tests for name list ordering and display."""

    def test_set_names_sorts_by_count_desc_and_suffixes_display(self, qapp):
        """First column shows `name (count)` sorted by count descending."""
        model = NameTableModel()
        model.set_names(
            ["Alice", "Bob", "Carol"],
            {"Alice": 2, "Bob": 5, "Carol": 1},
        )

        displayed = [
            model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole),
            model.data(model.index(1, 0), Qt.ItemDataRole.DisplayRole),
            model.data(model.index(2, 0), Qt.ItemDataRole.DisplayRole),
        ]

        assert displayed == ["Bob (5)", "Alice (2)", "Carol (1)"]

    def test_mappings_use_raw_name_not_display_suffix(self, qapp):
        """Replacement mappings keep the original raw name key."""
        model = NameTableModel()
        model.set_names(["Alice"], {"Alice": 3})

        assert model.setData(model.index(0, 1), "Alicia")
        assert model.get_edited_mappings() == {"Alice": "Alicia"}

    def test_append_custom_row_editable_both_columns(self, qapp):
        """User-added rows contribute mappings when find and replace differ."""
        model = NameTableModel()
        model.set_source_text("foo bar foo")
        model.append_custom_row()

        assert model.rowCount() == 1
        assert model.flags(model.index(0, 0)) & Qt.ItemFlag.ItemIsEditable
        assert model.flags(model.index(0, 1)) & Qt.ItemFlag.ItemIsEditable

        assert model.setData(model.index(0, 0), "foo")
        assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == "foo (2)"
        assert model.setData(model.index(0, 1), "FOO")
        assert model.get_edited_mappings() == {"foo": "FOO"}

    def test_set_source_text_does_not_recount_extracted_rows(self, qapp):
        """Rows from extraction preserve worker-provided counts."""
        model = NameTableModel()
        model.set_names(["Alice"], {"Alice": 7})

        model.set_source_text("Alice")

        assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == "Alice (7)"
