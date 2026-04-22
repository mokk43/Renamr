"""Format-agnostic ``Document`` abstraction.

The UI holds a single ``current_doc: Document | None`` and delegates format
specifics (extraction text source, save path, label fields, normalize
applicability) to the concrete subclass.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from txt_process.core.chunking import split_into_chunks
from txt_process.core.epub_io import EpubDocument as _EpubSnapshot
from txt_process.core.epub_io import load_epub, save_epub_with_replacements
from txt_process.core.io import load_text_file, save_text_file
from txt_process.core.replace import apply_replacements

DocumentKind = Literal["txt", "epub"]


class Document(ABC):
    """Common interface for all loadable input files."""

    path: Path
    text: str
    kind: DocumentKind
    encoding: str | None
    supports_normalize: bool
    display_info: str

    @abstractmethod
    def save_processed(
        self,
        mappings: dict[str, str],
        output_path: Path,
    ) -> tuple[dict[str, int], dict[str, dict[str, int]] | None]:
        """Apply ``mappings`` and save a processed copy to ``output_path``.

        Returns ``(totals, per_item)`` where ``per_item`` is ``None`` for
        formats that don't have a natural sub-file granularity (``.txt``).
        """


@dataclass
class TextDocument(Document):
    """Plain ``.txt`` input."""

    path: Path
    text: str
    encoding: str
    display_info: str
    kind: DocumentKind = field(default="txt", init=False)
    supports_normalize: bool = field(default=True, init=False)

    def save_processed(
        self,
        mappings: dict[str, str],
        output_path: Path,
    ) -> tuple[dict[str, int], dict[str, dict[str, int]] | None]:
        result_text, counts = apply_replacements(self.text, mappings)
        save_text_file(output_path, result_text, self.encoding)
        return counts, None


@dataclass
class EpubDocument(Document):
    """EPUB input wrapper delegating to :mod:`txt_process.core.epub_io`."""

    path: Path
    text: str
    version: str
    chapter_count: int
    size_bytes: int
    display_info: str
    kind: DocumentKind = field(default="epub", init=False)
    supports_normalize: bool = field(default=False, init=False)
    encoding: str | None = field(default=None, init=False)

    @classmethod
    def from_snapshot(cls, snap: _EpubSnapshot) -> EpubDocument:
        return cls(
            path=snap.path,
            text=snap.text,
            version=snap.version,
            chapter_count=snap.chapter_count,
            size_bytes=snap.size_bytes,
            display_info=snap.display_info,
        )

    def _snapshot(self) -> _EpubSnapshot:
        """Reconstruct a read-only snapshot for ``epub_io`` helpers."""
        return _EpubSnapshot(
            path=self.path,
            text=self.text,
            version=self.version,
            chapter_count=self.chapter_count,
            size_bytes=self.size_bytes,
            display_info=self.display_info,
        )

    def save_processed(
        self,
        mappings: dict[str, str],
        output_path: Path,
    ) -> tuple[dict[str, int], dict[str, dict[str, int]] | None]:
        totals, per_item = save_epub_with_replacements(
            self._snapshot(), mappings, output_path
        )
        return totals, per_item


def _build_txt_display_info(path: Path, text: str, encoding: str) -> str:
    size_kb = path.stat().st_size / 1024
    line_count = text.count("\n") + 1
    chunk_count = len(split_into_chunks(text))
    return (
        f"{path.name} | {size_kb:.1f} KB | {line_count} lines | "
        f"{chunk_count} chunks | {encoding}"
    )


def load_document(path: Path) -> Document:
    """Load a :class:`Document` by inspecting ``path``'s suffix."""
    if path.suffix.lower() == ".epub":
        snap = load_epub(path)
        return EpubDocument.from_snapshot(snap)

    text, encoding = load_text_file(path)
    return TextDocument(
        path=path,
        text=text,
        encoding=encoding,
        display_info=_build_txt_display_info(path, text, encoding),
    )
