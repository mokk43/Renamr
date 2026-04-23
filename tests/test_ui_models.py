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

    def test_set_names_filters_zero_occurrence_rows(self, qapp):
        """Zero-occurrence extracted names are not shown in the table."""
        model = NameTableModel()
        model.set_names(
            ["Alice", "Bob", "Carol"],
            {"Alice": 2, "Bob": 0, "Carol": 1},
        )

        displayed = [
            model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole),
            model.data(model.index(1, 0), Qt.ItemDataRole.DisplayRole),
        ]

        assert model.rowCount() == 2
        assert displayed == ["Alice (2)", "Carol (1)"]

    def test_set_names_recomputes_counts_with_replace_rules(self, qapp):
        """Extraction rows use replacement-matching counts, not raw worker counts."""
        model = NameTableModel()
        model.set_source_text("Alice met ALICE.")
        # Simulate worker-side substring counting that could report 0 for lowercase.
        model.set_names(["alice"], {"alice": 0})

        assert model.rowCount() == 1
        assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == "alice (2)"

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

    def test_zero_count_rows_are_not_used_for_mappings(self, qapp):
        """Edited rows with zero occurrences are ignored on export."""
        model = NameTableModel()
        model.set_source_text("Alice appears here.")
        model.append_custom_row()

        assert model.setData(model.index(0, 0), "Ghost")
        assert model.setData(model.index(0, 1), "Phantom")
        assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == "Ghost (0)"
        assert model.get_edited_mappings() == {}

    def test_set_name_pairs_filters_zero_occurrence_rows(self, qapp):
        """Imported pairs with zero occurrences are dropped."""
        model = NameTableModel()
        model.set_source_text("Alice met Alice.")
        model.set_name_pairs([("Alice", "Alicia"), ("Bob", "Bobby")])

        assert model.rowCount() == 1
        assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == "Alice (2)"
        assert model.data(model.index(0, 1), Qt.ItemDataRole.DisplayRole) == "Alicia"

    def test_set_source_text_does_not_recount_extracted_rows(self, qapp):
        """Rows from extraction preserve worker-provided counts."""
        model = NameTableModel()
        model.set_names(["Alice"], {"Alice": 7})

        model.set_source_text("Alice")

        assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == "Alice (7)"
