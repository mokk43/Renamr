"""Qt models for the name mapping table."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


@dataclass
class NameRow:
    """A single row in the name mapping table."""

    original: str
    replacement: str = ""
    occurrence_count: int = 0
    #: When True, the row was added by the user; column 0 (find text) is editable.
    user_added: bool = False

    @property
    def is_edited(self) -> bool:
        """True when this row contributes a find → replace mapping for export."""
        orig = self.original.strip()
        if not orig:
            return False
        rep = self.replacement.strip()
        return bool(rep) and rep != orig


class NameTableModel(QAbstractTableModel):
    """Model for the two-column name mapping table."""

    HEADERS = ["Original Name (Count)", "Replacement Name"]

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[NameRow] = []
        self._source_text: str = ""

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
                if role == Qt.ItemDataRole.EditRole and row.user_added:
                    return row.original
                label = row.original if row.original.strip() else "—"
                return f"{label} ({row.occurrence_count})"
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

        row = self._rows[index.row()]
        col = index.column()

        if col == 1:
            row.replacement = str(value)
            self.dataChanged.emit(index, index, [role])
            return True

        if col == 0 and row.user_added:
            row.original = str(value)
            row.occurrence_count = self._count_occurrences(row.original)
            top_left = self.index(index.row(), 0)
            bottom_right = self.index(index.row(), 1)
            self.dataChanged.emit(
                top_left,
                bottom_right,
                [role, Qt.ItemDataRole.DisplayRole],
            )
            return True

        return False

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        """Return item flags for the given index."""
        base_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return base_flags
        row = self._rows[index.row()]
        if index.column() == 1:
            return base_flags | Qt.ItemFlag.ItemIsEditable
        if index.column() == 0 and row.user_added:
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

    def set_names(self, names: list[str], counts: dict[str, int] | None = None) -> None:
        """Set names and optional occurrence counts, sorting by count desc."""
        counts = counts or {}
        ordered_names = sorted(names, key=lambda name: (-counts.get(name, 0), name))

        self.beginResetModel()
        self._rows = [
            NameRow(original=name, occurrence_count=counts.get(name, 0))
            for name in ordered_names
        ]
        self.endResetModel()

    def set_source_text(self, text: str) -> None:
        """Remember source text for occurrence counts (user-added and refresh)."""
        self._source_text = text
        self.refresh_occurrence_counts()

    def _count_occurrences(self, original: str) -> int:
        if not original:
            return 0
        return self._source_text.count(original)

    def refresh_occurrence_counts(self) -> None:
        """Recompute counts from source text for user-added rows only."""
        if not self._rows:
            return
        for i, row in enumerate(self._rows):
            if not row.user_added:
                continue
            new_count = self._count_occurrences(row.original)
            if new_count != row.occurrence_count:
                row.occurrence_count = new_count
                top_left = self.index(i, 0)
                bottom_right = self.index(i, 1)
                self.dataChanged.emit(
                    top_left,
                    bottom_right,
                    [Qt.ItemDataRole.DisplayRole],
                )

    def append_custom_row(self) -> None:
        """Append an empty user-editable row (both columns) at the bottom."""
        row_idx = len(self._rows)
        self.beginInsertRows(QModelIndex(), row_idx, row_idx)
        self._rows.append(
            NameRow(
                original="",
                replacement="",
                occurrence_count=0,
                user_added=True,
            )
        )
        self.endInsertRows()

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
