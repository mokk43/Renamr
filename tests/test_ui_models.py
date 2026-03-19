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
