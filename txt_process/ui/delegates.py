"""Qt delegates used by table views."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QCompleter, QStyledItemDelegate, QWidget


class ReplacementNameDelegate(QStyledItemDelegate):
    """Editable combobox delegate with dropdown suggestions for replacement names."""

    def __init__(self, suggestions: list[str] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._suggestions: list[str] = suggestions or []

    def set_suggestions(self, suggestions: list[str]) -> None:
        """Replace autocomplete suggestion values."""
        self._suggestions = suggestions

    def createEditor(self, parent, option, index):  # noqa: D401, ANN001
        """Create the cell editor."""
        combo = QComboBox(parent)
        combo.setEditable(True)
        combo.addItems(self._suggestions)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)

        completer = QCompleter(self._suggestions, combo)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        combo.setCompleter(completer)
        return combo

    def setEditorData(self, editor, index):  # noqa: D401, ANN001
        """Load current model value into the editor."""
        value = index.model().data(index, Qt.ItemDataRole.EditRole) or ""
        editor.setEditText(str(value))

    def setModelData(self, editor, model, index):  # noqa: D401, ANN001
        """Write editor value back to model."""
        model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)

