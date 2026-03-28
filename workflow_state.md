# Workflow State

## Status
`NEEDS_PLAN_APPROVAL`

## Plan
BLUEPRINT - Large-document sampled extraction spec alignment:
- Update `AGENTS.md` product flow + extraction contract to explicitly allow sampled extraction for large documents:
  - small docs: serial one-call-per-chunk with minimum interval
  - large docs: phased sampling (seed scan, local scan, targeted fill)
- Update `AGENTS.md` testing requirements so cadence is validated on sampled LLM calls and add expectations for phase behavior.
- Update tests to reflect the new contract:
  - remove assumptions that every chunk must always call the model
  - add unit tests for phased selection and no-retry behavior in sampled mode
- Re-review current uncommitted patch against the revised contract and report remaining issues.

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
