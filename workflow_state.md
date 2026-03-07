# Workflow State

## Status
`IN_PROGRESS`

## Plan
BLUEPRINT - Ollama protocol routing:
- Add endpoint detector for Ollama (`port 11434`) in `txt_process/core/llm_client.py`
- Introduce dual protocol path:
  - OpenAI-compatible: existing `chat.completions` call path
  - Ollama-native: `/api/generate` JSON protocol path
- Route by settings `base_url`; if Ollama endpoint, use Ollama-native path
- Reuse endpoint detector in UI API-key gate (`txt_process/ui/main_window.py`)
- Add tests to prove protocol selection and request payload correctness

## Log
- Started Ollama protocol enhancement blueprint
- Scaffold created: pyproject.toml, README, package structure
- Core modules: io.py, chunking.py, llm_client.py, name_extract.py, replace.py, config.py
- UI modules: main_window.py, settings_dialog.py, models.py, workers.py
- Tests: chunking, parsing, cadence, replacement, I/O
- QA: All acceptance criteria verified, lint-free, .gitignore added

## Acceptance Criteria Verification
- [x] Can select and load `.txt` reliably (handles encoding errors gracefully)
- [x] Splits into ordered chunks, each strictly <16KB UTF-8 bytes
- [x] Calls OpenAI-compatible model serially, one chunk per request, ≥2s between requests
- [x] Dedupe merges extracted names into a list shown in a 2-column editable UI
- [x] Only edited mappings are replaced; export file name follows `*_processed` rule
- [x] LLM settings + prompt persist and auto-load on startup
