# AGENTS.md — Txt Character Renamer

This document defines the **product requirements**, **architecture**, and **coding conventions** for building a Python GUI tool that:

- Loads a `.txt` file
- Calls an **OpenAI-compatible** LLM (serially, **1 chunk at a time**, **≥2s** between requests) to extract a **character/name list**
- Lets the user edit name mappings in a **2-column editable grid**
- Replaces only the edited names in the original text and exports `*_processed.txt`
- Provides a settings UI for LLM + prompt configuration and persists it to disk

This file is the source of truth for agent work in this repo.

---

## Product summary (from PRD)

### Core user flow
- **Select file**: user chooses a `.txt`.
- **Extract names**: app chunk-splits the document into blocks **<16KB** and sends chunks to the LLM **in order**. **One request per chunk** with **2 seconds** delay between requests.
- **Review/edit mapping**: app dedupes all extracted names into a list. UI shows a **two-column table**:
  - Column A: **original name** (read-only)
  - Column B: **replacement name** (editable input)
- **Replace/export**: on “Replace”, app replaces only the names whose replacement was edited (and non-empty per rules) and exports to a new file:
  - `original_filename_processed.txt` (suffix inserted before extension)
- **Configure LLM**: UI allows configuring OpenAI-compatible connection fields and the extraction prompt; config is persisted and loaded on startup.

### Explicit constraints (must not violate)
- **Chunk size**: each chunk must be **strictly < 16KB** (by bytes, UTF-8).
- **Chunk composition**: each chunk consists of **one or more consecutive paragraphs** (preserve order).
- **LLM calls**: **serial**; **one chunk per request**; **2 seconds** between requests (minimum).

---

## Tech stack (decision)

### GUI framework
- **PySide6 (Qt for Python)** is the default GUI framework.
  - Rationale: robust tables (`QTableView` + `QAbstractTableModel`), good cross-platform behavior, stable threading primitives (`QThread`/signals).

### LLM client
- Use the official **OpenAI Python SDK** (OpenAI-compatible via `base_url`) **or** plain `httpx` if SDK constraints arise.
- Must support:
  - `base_url`
  - `api_key`
  - `model`
  - `temperature`
  - optional `timeout`, `max_tokens`

### Config & secrets
- Persist app config as **JSON** in user config directory via `platformdirs`.
- API key handling:
  - Default: **do not persist** plaintext keys in JSON.
  - If “Remember API key” is implemented: use **keyring** (OS keychain).

### Formatting & lint
- **black** for formatting, **ruff** for linting, **pytest** for tests.
- Use type hints throughout (Python 3.11+ preferred).

---

## Repository conventions (layout)

Preferred layout:

- `txt_process/`
  - `__init__.py`
  - `main.py` (entrypoint)
  - `ui/` (Qt windows, dialogs, widgets)
  - `core/`
    - `chunking.py` (paragraph split + <16KB chunker)
    - `llm_client.py` (OpenAI-compatible client wrapper)
    - `name_extract.py` (prompting + parse/normalize/dedupe)
    - `replace.py` (replacement plan + apply replacement)
    - `config.py` (load/save config, keyring integration)
    - `io.py` (read/write text with encoding strategy)
  - `resources/` (icons, etc. optional)
- `tests/` (pytest)
- `AGENTS.md`

Keep GUI code thin; business logic lives under `core/`.

---

## Data contracts (must be stable)

### Config schema (JSON)
Store at `platformdirs.user_config_dir(appname)/config.json`.

Fields (minimum):
- `base_url: str`
- `model: str`
- `temperature: float`
- `timeout_seconds: float | int` (optional)
- `max_tokens: int` (optional)
- `prompt_template: str` (used for extraction)
- `chunk_max_bytes: int` (default: 16384; enforce strict `< chunk_max_bytes`)
- `request_interval_seconds: float` (fixed default: 2.0; enforce minimum)
- `remember_api_key: bool` (optional)
- `api_key_id: str` (optional reference if using keyring; never store the key itself)

### Name mapping row model
Each deduped name becomes a row:
- `original_name: str`
- `replacement_name: str` (editable; may start empty)
- `edited: bool` (true if user changed replacement to a non-empty different value)
- `replace_count: int` (computed at export time; optional for UI)

---

## Chunking specification (critical)

### Paragraph splitting
- A **paragraph** is a run of non-empty lines separated by one or more blank lines.
- Preserve paragraph internal newlines.

### Chunk formation (strict)
- Build chunks as **consecutive paragraph groups** in original order.
- Measure size by **UTF-8 encoded bytes**.
- Every chunk must satisfy: `0 < len(chunk_bytes) < 16 * 1024`.

### Oversized paragraph fallback
If a single paragraph exceeds the limit:
- Split it into sub-chunks by bytes (UTF-8), preserving order.
- These “forced split” chunks must still satisfy `< 16KB`.
- Ensure the UI/progress still reflects correct chunk indexing.

### Safety margin
When using prompt templates, keep chunk text itself `< 16KB` regardless of prompt size.
Do not attempt to fit prompt+chunk under the limit unless the model/provider requires it; the PRD constraint is explicitly on paragraph blocks.

---

## LLM extraction specification (critical)

### Calling pattern
- One request per chunk.
- Requests are **serial**; no concurrency.
- Enforce **minimum 2.0 seconds** between request *starts* (use monotonic clock).

### Prompting contract
The extraction prompt must strongly constrain output to a parseable format.
Required output format:
- **Strict JSON** with this shape:
  - `{"names": ["Name1", "Name2", ...]}`

If the provider returns text around JSON, implement robust extraction:
- Prefer strict JSON parsing; if it fails, attempt to locate the first JSON object and parse.
- If still failing, do **one** corrective retry that instructs the model to output only strict JSON.

### Dedupe & normalization rules
At minimum:
- Trim whitespace.
- Drop empty strings.
- Exact-match dedupe after normalization.

Optional (only if explicitly enabled in config/UI):
- Normalize full-width/half-width.
- Case-folding for Latin names.

---

## Replacement/export specification (critical)

### Replacement eligibility
- Replace only if the user provided a **non-empty** replacement **different** from original.
- Unedited rows must not cause replacements.

### Replacement ordering (avoid overlap bugs)
When applying multiple replacements:
- Sort original names by **descending length** and replace in that order.
  - Prevents “张三” replacing inside “张三丰” before the longer token is handled.

### Replacement method
- Default: **exact substring replace** (no regex unless explicitly designed).
- Track counts per name and total.

### Output path/name
- New file name: insert `_processed` **before** extension.
  - `story.txt` → `story_processed.txt`
  - `story` (no extension) → `story_processed`
- Default output directory: same as input file.
- If write fails (permissions), prompt user to choose output directory.

---

## UI/UX requirements (implementation rules)

### Main window must provide
- File selection control + file metadata.
- Buttons:
  - “Extract names”
  - “Replace / Export”
  - “Settings…”
- Progress indicator:
  - chunk `i / N`
  - current status (“Waiting 2s…”, “Calling model…”, “Parsing…”, “Done”, error)
- Two-column editable table:
  - Column A read-only (original)
  - Column B editable (replacement)
  - Optional helpers:
    - filter “edited only”
    - search box
    - reset row / reset all

### Responsiveness (must)
- Never block the GUI thread during:
  - chunking large files
  - LLM calls (including the 2-second waits)
  - export/replace on large texts
- Use a worker thread (`QThread`) with signals for progress + results.

### Logging/errors (must)
- Present user-friendly error messages.
- Provide a collapsible log panel for detailed diagnostics.
- Never log full API keys.

---

## Testing requirements

### Unit tests (minimum set)
- **Chunking**
  - paragraphs → chunks `<16KB`
  - oversized paragraph fallback works and preserves order
- **LLM cadence**
  - enforce serial calling
  - enforce ≥2 seconds between calls (test via injected clock/sleep abstraction)
- **Parsing**
  - strict JSON parsing
  - “JSON wrapped in text” extraction
  - corrective retry behavior (mocked)
- **Dedupe**
  - trimming + empty removal + exact dedupe
- **Replacement**
  - only edited/non-empty replacements applied
  - overlap safety (length-desc order)
  - output naming `_processed` insertion

### Test environment convention (do not auto-install deps)
If this is a Python project, testing should assume the user activates their environment via:

```bash
source ~/workspace/buildingai/bin/activate
```

Do not run `pip install` automatically in agent actions unless explicitly requested.

---

## Agent workflow constraints (how to work in this repo)

### Planning discipline
- Before implementation work, write a short **BLUEPRINT** in `workflow_state.md` (if/when it exists) describing modules + data flow + edge cases.
- Set `State.Status = NEEDS_PLAN_APPROVAL` before starting major construction work.

### Code quality rules
- Prioritize clarity and correctness over cleverness.
- No `TODO` placeholders in shipped code paths.
- All user-visible strings should be consistent and actionable.
- Avoid “magic numbers”: expose chunk limit and request interval via config (with safe defaults).

---

## Acceptance criteria (build must satisfy)
- Can select and load `.txt` reliably (handles encoding errors gracefully).
- Splits into ordered chunks, each **strictly <16KB** UTF-8 bytes.
- Calls OpenAI-compatible model **serially**, one chunk per request, **≥2s** between requests.
- Dedupe merges extracted names into a list shown in a **2-column editable** UI.
- Only edited mappings are replaced; export file name follows `*_processed` rule.
- LLM settings + prompt persist and auto-load on startup.

