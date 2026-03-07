"""Qt models for the name mapping table."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


@dataclass
class NameRow:
    """A single row in the name mapping table."""

    original: str
    replacement: str = ""

    @property
    def is_edited(self) -> bool:
        """Check if the replacement has been edited (non-empty and different)."""
        return bool(self.replacement.strip()) and self.replacement.strip() != self.original


class NameTableModel(QAbstractTableModel):
    """Model for the two-column name mapping table."""

    HEADERS = ["Original Name", "Replacement Name"]

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[NameRow] = []

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        """Return number of rows."""
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        """Return number of columns (always 2)."""
        return 2

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        """Return data for the given index and role."""
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None

        row = self._rows[index.row()]
        col = index.column()

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            if col == 0:
                return row.original
            else:
                return row.replacement

        if role == Qt.ItemDataRole.BackgroundRole:
            if col == 1 and row.is_edited:
                from PySide6.QtGui import QColor

                return QColor(255, 120, 10)  # Light blue for edited

        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole) -> bool:
        """Set data for the given index."""
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False

        if index.column() == 1:  # Only replacement column is editable
            self._rows[index.row()].replacement = str(value)
            self.dataChanged.emit(index, index, [role])
            return True

        return False

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        """Return item flags for the given index."""
        base_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 1:  # Replacement column is editable
            return base_flags | Qt.ItemFlag.ItemIsEditable
        return base_flags

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ):
        """Return header data."""
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.HEADERS):
                return self.HEADERS[section]
        return None

    def set_names(self, names: list[str]) -> None:
        """Set the list of original names, clearing any previous data."""
        self.beginResetModel()
        self._rows = [NameRow(original=name) for name in names]
        self.endResetModel()

    def get_edited_mappings(self) -> dict[str, str]:
        """Get a dict of original -> replacement for edited rows only."""
        return {row.original: row.replacement.strip() for row in self._rows if row.is_edited}

    def reset_all(self) -> None:
        """Clear all replacement values."""
        self.beginResetModel()
        for row in self._rows:
            row.replacement = ""
        self.endResetModel()

    def reset_row(self, index: int) -> None:
        """Clear replacement for a specific row."""
        if 0 <= index < len(self._rows):
            self._rows[index].replacement = ""
            idx = self.index(index, 1)
            self.dataChanged.emit(idx, idx)
