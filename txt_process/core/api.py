"""Public core API consumed by UI layers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from txt_process.core.config import Config, load_config, save_config
from txt_process.core.document import Document, load_document
from txt_process.core.extraction import (
    ExtractionCallbacks,
    ExtractionCancelled,
    ExtractionResult,
    ProgressEvent,
    run_extraction,
)
from txt_process.core.name_cache import load_name_cache, save_name_cache
from txt_process.core.normalize_txt import normalize_text_file
from txt_process.core.replace import build_output_path, count_name_occurrences


@dataclass(slots=True)
class ReplaceResult:
    """Result returned by replace/export helpers."""

    output_path: Path
    totals: dict[str, int]
    per_item: dict[str, dict[str, int]] | None = None


def extract_names(
    text: str,
    config: Config,
    api_key: str,
    callbacks: ExtractionCallbacks | None = None,
) -> ExtractionResult:
    """Extract names from document text."""
    return run_extraction(text=text, config=config, api_key=api_key, callbacks=callbacks)


def commit_name_pairs(document: Document, pairs: list[tuple[str, str]]) -> None:
    """Reserved seam for committing post-extraction mappings."""
    _ = document
    _ = pairs


def commit_imported_pairs(
    document: Document, pairs: list[tuple[str, str]]
) -> tuple[list[tuple[str, str]], dict[str, int]]:
    """Filter imported source-target rows to names present in the document."""
    counts = {
        source: count_name_occurrences(document.text, source) for source, _ in pairs if source
    }
    filtered = [pair for pair in pairs if counts.get(pair[0], 0) > 0]
    return filtered, counts


def replace_and_export(
    document: Document,
    mappings: dict[str, str],
    output_path: Path | None = None,
) -> ReplaceResult:
    """Apply mappings and write processed output."""
    resolved_output = output_path or build_output_path(document.path)
    totals, per_item = document.save_processed(mappings, resolved_output)
    return ReplaceResult(output_path=resolved_output, totals=totals, per_item=per_item)


def read_settings() -> Config:
    """Read persisted application settings."""
    return load_config()


def write_settings(config: Config) -> None:
    """Persist application settings."""
    save_config(config)


def normalize_layout(input_path: Path, output_path: Path) -> None:
    """Normalize wrapped txt layout and write to ``output_path``."""
    normalize_text_file(str(input_path), str(output_path))


__all__ = [
    "Config",
    "Document",
    "ExtractionCallbacks",
    "ExtractionCancelled",
    "ExtractionResult",
    "ProgressEvent",
    "ReplaceResult",
    "commit_imported_pairs",
    "commit_name_pairs",
    "extract_names",
    "load_document",
    "load_name_cache",
    "normalize_layout",
    "read_settings",
    "replace_and_export",
    "save_name_cache",
    "write_settings",
]
