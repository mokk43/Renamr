# Workflow State

## Status
`IN_PROGRESS`

## Plan
BLUEPRINT - macOS SwiftUI shell + XPC scaffold (U6 onward):
- Scaffold `macos/` project layout for `Renamr` app + `RenamrPythonService` service.
  - Add Swift sources for protocol DTOs, service actor, progress receiver, and initial SwiftUI app/viewmodel/views.
- Add vendoring and release scripts under `macos/Scripts/` (`vendor_python.sh`, signing/notarize/dmg/appcast wrappers).
- Add Python bridge package `txt_process/macos_bridge/`:
  - Request dispatcher, progress callback adapter, cancellation token registry, and error mapping.
- Add Python tests for the bridge (`tests/test_macos_bridge.py`) and keep full pytest green.
- Keep plan-unit progression explicit in code and validate changed Python code with ruff + black + pytest.

## Log
- 2026-06-09: Started ce-work execution for plan `2026-06-08-001-feat-macos-swiftui-shell-plan.md` (U1-U4 tranche).
- 2026-06-09: Continuing ce-work execution from U6 onward (macOS scaffold + bridge + packaging scripts).
- 2026-06-09: Implemented Swift package scaffold for Renamr app + XPC service, shared DTO/protocol/error contracts, SwiftUI view models/views, and release scripts.
- 2026-06-09: Implemented Python bridge dispatcher and tests (`tests/test_macos_bridge.py`), then validated with scoped lint/format checks and full pytest.
- 2026-06-09: Validated Swift side with `swift build` and `swift test` under `macos/`.
- 2026-06-09: Updated plan unit statuses, U6/U7/U9/U10/U12-U16 marked completed, U8/U11/U17-U19 remain in progress pending remaining integration and release verification.
- 2026-06-09: Wired Python runtime discovery for bundled vendored runtime paths, added `prepare_python_runtime.sh`, and hardened Swift XPC client timeout/error handling with reconnect reset behavior.
- 2026-06-09: Revalidated post-hardening changes (`swift build`, `swift test`, `pytest -q`, and script syntax checks) and refreshed U8/U11/U17 status notes in the plan doc.
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
