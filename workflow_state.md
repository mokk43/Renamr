# Workflow State

## Status
`NEEDS_PLAN_APPROVAL`

## Plan
BLUEPRINT - Local replacement-name cache and autocomplete:
- Add `txt_process/core/name_cache.py` to persist a deduped replacement-name list in the user app config folder (`platformdirs`) as JSON.
  - Provide load/save/merge helpers.
  - Trim whitespace, drop empties, exact dedupe.
- Add replacement-column autocomplete:
  - Introduce a Qt item delegate for column B that uses an editable combo box.
  - Keep free typing enabled while offering dropdown suggestions from cached names.
- Add settings editor support for cache:
  - In Settings dialog, add a multiline editor (one name per line) to manually manage cached names.
  - Save edits back to cache file on dialog accept.
- Auto-update cache when users enter new replacement names in the table:
  - Observe table edits, merge any new non-empty replacement names into cache, persist, and refresh autocomplete options.
- Add tests for cache module behavior (load/save/merge/dedupe).

## Log
- Started Ollama protocol enhancement blueprint
- Scaffold created: pyproject.toml, README, package structure
- Core modules: io.py, chunking.py, llm_client.py, name_extract.py, replace.py, config.py
- UI modules: main_window.py, settings_dialog.py, models.py, workers.py
- Tests: chunking, parsing, cadence, replacement, I/O
- QA: All acceptance criteria verified, lint-free, .gitignore added
- Updated workflow blueprint for sampled extraction contract alignment

## Acceptance Criteria Verification
- [x] Can select and load `.txt` reliably (handles encoding errors gracefully)
- [x] Splits into ordered chunks, each strictly <16KB UTF-8 bytes
- [x] Calls OpenAI-compatible model serially, one chunk per request, ≥2s between requests
- [x] Dedupe merges extracted names into a list shown in a 2-column editable UI
- [x] Only edited mappings are replaced; export file name follows `*_processed` rule
- [x] LLM settings + prompt persist and auto-load on startup
