# Add EPUB support to Renamr
## Problem
Renamr currently only processes `.txt` files. We want to accept `.epub` files, run the same LLM-driven name extraction and user-edited replacement workflow, and export a new `.epub` (`*_processed.epub`) that preserves the book's structure (chapters, CSS, images, TOC) — only the text nodes inside XHTML are rewritten.
## Current state (relevant bits)
* Load path: `MainWindow._on_select_file` → `load_text_file` → stores `current_text: str` and `current_encoding: str` on the window (`txt_process/ui/main_window.py:231`, `txt_process/core/io.py:10`).
* Extraction pipeline is purely string-based: `split_into_chunks(text)` → LLM per chunk → dedupe (`txt_process/core/chunking.py`, `txt_process/ui/workers.py`). It has no knowledge of file format and does not need to change.
* Replace path: `apply_replacements(text, mappings)` does length-desc substring replace; `build_output_path` inserts `_processed` before the suffix (`txt_process/core/replace.py`). It is already format-agnostic and will yield `story_processed.epub` for an epub input.
* Normalize Layout is txt-specific (`txt_process/core/normalize_txt.py`) — out of scope for EPUB.
* No existing abstraction over "document" — the UI directly holds `current_text`/`current_encoding`.
## Proposed changes
### 1. New EPUB I/O module: `txt_process/core/epub_io.py`
Wraps an EPUB file and exposes the two touch points the rest of the app needs.
* `EpubDocument` (concrete `Document` subclass, see §2) holding only immutable, load-time values — the parsed `EpubBook` is intentionally NOT retained so there is no shared mutable state between load and save (simpler than a `reload()` method and eliminates idempotence footguns):
    * `path: Path`
    * `text: str` — concatenation of **spine items only** (so off-spine front/back matter cannot pollute LLM input). Sections joined with a blank line so the existing paragraph/chunker sees clean paragraph boundaries. `<script>`, `<style>`, `<head>` excluded.
    * `version: str` — EPUB version for display.
    * `chapter_count: int` — `len(book.spine)` (matches reader mental model).
    * `size_bytes: int` — `path.stat().st_size` (on-disk size, matches Finder; not `len(text)`).
    * `display_info: str` — pre-computed file-info label string, so UI refresh never re-runs `split_into_chunks`.
* Typed exceptions (raised by `load_epub` / `save_epub_with_replacements`): `EpubEncryptedError`, `EpubParseError`, `EpubEmptyError`. UI maps each to a targeted message.
* `load_epub(path: Path) -> EpubDocument`
    * Pre-flight: open the EPUB as a zip and raise `EpubEncryptedError` if `META-INF/encryption.xml` is present.
    * Uses `ebooklib.epub.read_epub(path)`; silences `ebooklib` `ImportWarning`/`UserWarning` at import time via `warnings.filterwarnings`. Wraps any underlying parse failure in `EpubParseError`.
    * Parses every spine `ITEM_DOCUMENT` with `BeautifulSoup(raw, "lxml-xml")` (XHTML-strict). Extracts visible text in document order, excluding `<script>`, `<style>`, `<head>`.
    * Does NOT retain the `EpubBook` object.
* `save_epub_with_replacements(doc: EpubDocument, mappings: dict[str, str], output_path: Path) -> tuple[dict[str, int], dict[str, dict[str, int]]]`
    * Re-reads the source via `read_epub(doc.path)` so replacement is always performed against pristine content, independent of anything held in memory.
    * **Replacement scope** is broader than extraction scope: every `ITEM_DOCUMENT` in the manifest **plus** every `ITEM_NAVIGATION` item. For NCX specifically the rewritten `<text>` nodes live under `<navMap>/<navPoint>/<navLabel>`, `<pageList>/.../<navLabel>`, `<navList>/.../<navLabel>`, `<docTitle>`, and `<docAuthor>` (otherwise the TOC/author still show old names after export). Non-XHTML/NCX items (CSS, images, fonts, audio) are skipped entirely and their bytes pass through untouched.
    * For each XHTML/NCX item: parses with `lxml-xml`, walks `NavigableString`s inside `<body>` and `<title>` (XHTML) or the NCX `<text>` nodes listed above (excluding `<script>`/`<style>`), and calls `core.replace.apply_replacements` on each node's string. Per-item and global counts accumulate from **actual node replacements performed** — this is the authoritative number shown to the user (no preview-text mismatch). Per-item keys in the returned dict are `item.file_name` (e.g. `OEBPS/ch03.xhtml`) so log lines are human-recognizable.
    * **Adjacent-text-node coalescing**: before replacement, coalesces runs of adjacent `NavigableString`s that share a parent of type `span`, `em`, `i`, `b`, `strong`, `u`, `small`, `sub`, `sup`, `mark` (phrasing inlines) into a single node so names split by inline wrappers (`<span>张</span><span>三</span>`) are still matched. Safety rules to avoid destroying styling:
        * Coalesce only when the parent elements share **both the same tag and the same attribute set** — otherwise skip the boundary and emit a debug log line `"skipped coalesce: <span class='red'>"`.
        * Never coalesce into or across whitespace-only `NavigableString`s (prevents accidentally merging logically-separate paragraphs).
        * Ruby annotations (`ruby`/`rt`/`rp`) are intentionally NOT coalesced — names split across ruby are documented as a known limitation.
    * Serializes each modified item with `str(soup).encode("utf-8")`. DOCTYPE preservation: for NCX (and any XHTML with `<!DOCTYPE html>`), capture the `Doctype` node at parse time and re-prepend it when writing (`doctype_bytes + b"\n" + str(soup).encode("utf-8")`) — BeautifulSoup's `lxml-xml` serialization otherwise drops the DOCTYPE. Then `item.set_content(...)`.
    * Calls `ebooklib.epub.write_epub(output_path, book)`.
    * Returns `(totals, per_item)` — totals for legacy log compatibility, per-item for the granular log line (see §3).
* Attribute policy: only `NavigableString` text and `<title>`/NCX `<text>` content are rewritten. `href`, `src`, `id`, `class`, `epub:type`, `alt`, `aria-label`, `title=` are NOT touched (documented; reconsidered in a future iteration).
### 2. Document abstraction: `txt_process/core/document.py`
Introduce a small ABC (not a `Protocol` — avoids `@runtime_checkable` friction and matches the repo's dataclass-ish style) so the UI can stop special-casing formats.
* `class Document(ABC)` with attributes `path: Path`, `text: str`, `kind: Literal["txt", "epub"]`, `encoding: str | None`, `supports_normalize: bool`, `display_info: str` (pre-computed at load), and abstract `save_processed(mappings, output_path) -> tuple[dict[str, int], dict[str, dict[str, int]] | None]`.
* `TextDocument` — thin wrapper around `load_text_file` / `save_text_file`; `save_processed` runs `apply_replacements` then `save_text_file`, returns `(counts, None)`. `supports_normalize = True`. `display_info` formatted as today: `name | size KB | N lines | M chunks | encoding`.
* `EpubDocument` (implemented in `epub_io`, re-exported here) — `supports_normalize = False`, returns `(totals, per_item)` from `save_processed`. `display_info` formatted as `name | size KB | N chapters | M chunks | EPUB vX.Y`.
* `load_document(path: Path) -> Document` dispatches by suffix (`.epub` → `EpubDocument`, else `TextDocument`).
### 3. UI changes (`txt_process/ui/main_window.py` + `txt_process/ui/workers.py`)
* Replace `current_file` / `current_text` / `current_encoding` attributes with a single `current_doc: Document | None`. Keep `current_text` as a computed property pointing to `current_doc.text` for minimal churn in extraction/worker code.
* File dialog filter: `"Supported (*.txt *.epub);;Text Files (*.txt);;EPUB Books (*.epub);;All Files (*)"`.
* `_set_active_file` runs on a background thread via a new `LoadDocumentWorker` (mirrors `ExtractNamesWorker`'s QThread + signals pattern). The worker emits `progress(i, total, f"Parsing {item.file_name}")` per spine item so large books show continuous life instead of a frozen busy spinner. Cancel path supported.
* **Separate worker slots**: add `self.load_worker` / `self.load_worker_thread` fields distinct from the existing `self.worker` / `self.worker_thread` used for extraction. `_on_select_file` is disabled while either extraction OR a load is already running, so the two workers can never collide.
* File-info label reads directly from `Document.display_info` (pre-computed, no chunker re-run on refresh).
* Typed EPUB errors surface distinct messages: `EpubEncryptedError` → "This EPUB is DRM-protected and cannot be processed."; `EpubParseError` → "Failed to parse EPUB: …"; `EpubEmptyError` → "This EPUB contains no readable content."
* `_on_normalize`: the button is **hidden** (`setVisible(False)`) when `not current_doc.supports_normalize` — cleaner than greying it out and avoids "why is this disabled?" confusion. Visibility is restored when the user re-selects a txt. Existing behavior for txt preserved.
* `_on_replace`:
    * Delegates save to `current_doc.save_processed(mappings, output_path)` and logs totals plus, when per-item data is returned, one line per item (`[ch03.xhtml] 7 replacements`).
    * Default `output_path = build_output_path(current_doc.path)` (already yields `story_processed.epub`).
    * PermissionError fallback dialog: filter and default filename driven by `current_doc.kind` (`story_processed.epub` for epub, `story_processed.txt` for txt) so users don't accidentally strip/retype the extension; keeps `All Files (*)` as last filter option for parity with current behavior.
* Button enabled-state logic (`_update_button_states`) gains the `supports_normalize` check for `btn_normalize`.
### 4. Dependencies (`pyproject.toml`)
Add to `dependencies` (all hard, not optional — tests rely on `lxml-xml`):
* `ebooklib>=0.18`
* `beautifulsoup4>=4.12`
* `lxml>=5.0`
### 5. Tests (`tests/`)
* Programmatic EPUB fixture: `tests/conftest.py` gains a `build_sample_epub(tmp_path, *, adversarial: bool = False)` helper that uses `ebooklib` to construct small EPUBs at test time (no binary committed). The adversarial variant includes:
    * a `<style>` block that literally contains a target name (must NOT be replaced),
    * a chapter with `<span>张</span><span>三</span>` (verifies coalescing rule §1),
    * `张三` adjacent to `张三丰` (verifies length-desc overlap safety),
    * a `<title>` element containing a target name,
    * a `toc.ncx` entry referencing a target name (verifies EPUB 2 TOC replacement),
    * a CSS item and a PNG image item in the manifest for round-trip checks.
* `tests/test_epub_io.py`:
    * `load_epub` extracts text from spine items only (off-spine manifest docs excluded from LLM input), excludes script/style/head.
    * Typed errors: DRM pre-flight raises `EpubEncryptedError`; corrupt zip raises `EpubParseError`; empty spine raises `EpubEmptyError`.
    * Adversarial coalescing: split inline-wrapped name is matched and replaced.
    * Style/script content is NOT modified even when it contains the target name.
    * Length-desc overlap safety: `张三丰` intact when only `张三` is mapped.
    * NCX replacement: `toc.ncx` `<text>` nodes reflect the new names after save.
    * `save_epub_with_replacements` returns truthful totals equal to actual node replacements performed.
    * **Round-trip integrity**: re-reading the output EPUB confirms same manifest IDs, same spine order, byte-equal CSS and image item bytes (compared via `item.get_content()`, not parsed soup), and body text contains replacements.
    * **XML well-formedness**: every modified XHTML/NCX item in the output parses cleanly with `lxml.etree.fromstring` — guards against BeautifulSoup serialization regressions (missing XML declaration, namespace drift, `<br>` vs `<br/>`).
    * Idempotence: calling `save_processed` twice with different mappings against the same `EpubDocument` yields results consistent with each mapping applied to pristine source (book is always re-read internally).
* `tests/test_document.py`:
    * `load_document` dispatches by suffix.
    * `TextDocument.save_processed` regression matches existing txt behavior.
### 6. Documentation
* README: add EPUB to supported formats; note preserved-structure behavior, the inline-span coalescing, and ruby/attribute limitations.
* `AGENTS.md`: add a short "EPUB handling" subsection under Tech stack + Acceptance criteria (`*_processed.epub`, structure preserved, Normalize is txt-only, DRM rejected).
## Nice-to-have (not in this pass)
* Also replace inside `alt=`, `aria-label=`, and `title=` attributes behind a toggle.
* Pre-flight preview pane showing per-item replacement counts before writing.
* Replace across ruby annotations by merging `ruby`/`rt` text.
## Out of scope
* EPUB-specific layout normalization.
* Editing EPUB metadata (title/author) during export.
* Partial-book export or chapter-only replacement.
* Handling DRM-protected or font-obfuscated EPUBs (detected and rejected, not processed).
## Risks / open items
* `ebooklib` emits deprecation warnings on modern Python; filtered at import time.
* Very large EPUBs (>10MB text) still go through the 16KB chunker + 2s cadence rules — no perf work planned beyond the load-on-worker-thread change.
* Replacement is `O(N_text_nodes · N_mappings · avg_len)`. Fine for typical books (<100 names, <50K nodes) but could slow down on pathological inputs; acceptable for this pass, revisit if a real user hits it.
* Memory: `ebooklib.read_epub` reads the full compressed file into memory. Fine for typical books; pathological 500 MB+ EPUBs would spike RAM. Not mitigated in this pass.
