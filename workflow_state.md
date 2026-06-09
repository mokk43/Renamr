# Workflow State

## Status
`NEEDS_PLAN_APPROVAL`

## Plan
BLUEPRINT - Shared extraction facade and thin UI adapters:
- Add `txt_process/core/api.py` as the public entry point for UI consumers.
  - Re-export shared extraction/data types and provide wrappers for document load, settings persistence, cache, normalize, and replace/export.
- Add `txt_process/core/extraction.py` and move extraction orchestration out of Qt workers.
  - Keep serial/phased flow, cadence waits, corrective retry, rate-limit wait parsing, and callback-driven progress.
- Centralize API-key persistence policy in `txt_process/core/config.py`.
  - Persist blank key when `remember_api_key` is false, and defensively blank on load.
- Refactor `txt_process/ui/workers.py` and settings save path to thin adapters over `core.api`.
- Add/adjust tests (`test_api.py`, `test_extraction.py`, `test_config.py`, scenario round-trip) to lock behavior.

## Log
- 2026-06-09: Started ce-work execution for plan `2026-06-08-001-feat-macos-swiftui-shell-plan.md` (U1-U4 tranche).
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
