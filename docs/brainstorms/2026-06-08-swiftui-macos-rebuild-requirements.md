# SwiftUI macOS App with Embedded Python (XPC Sidecar) — Requirements

**Date:** 2026-06-08
**Status:** Approved scope; ready for `ce-plan`
**Branch:** `swiftui-pilot`

## Summary

Ship a native macOS app, `Renamr.app`, with a SwiftUI front-end and a bundled `RenamrPythonService.xpc` sidecar that hosts the existing `txt_process/core/` Python business logic behind a stable async protocol. Distribution is Developer ID + notarization; the PySide6 app continues to ship for Windows/Linux against the same `core/`.

## Driver / Why now

Current distribution path (PySide6 + PyInstaller, documented in `docs/PACKAGING_MACOS.md`) produces a working but un-native `.app`: ~150-200MB bundle, Qt look-and-feel on macOS, no first-class auto-update. The macOS rebuild targets three concrete wins:

- **Native feel** — SwiftUI controls, system fonts, standard macOS tables.
- **Smaller bundle** — drop Qt; target a meaningfully smaller `.app` (see Success Criteria).
- **Auto-update** — first-class updater (Sparkle or equivalent) instead of "re-download the dmg."

Mac App Store listing is explicitly **not** a goal, which removes the hardest constraint (App Sandbox + library-validation restrictions on embedded CPython).

## Primary actor + outcome

A macOS user who today downloads `Renamr.app` (PyInstaller build) and renames characters in a TXT/EPUB. After this work ships, they download a smaller, native-feeling `Renamr.app` from the project's distribution channel, complete the same end-to-end flow, and receive future updates automatically.

## Goals

1. Full feature parity with the current PySide6 app on day one (see Functional Requirements).
2. Preserve every Renamr correctness invariant byte-for-byte (see Invariants).
3. Process-isolated Python: a crash in the Python sidecar must not kill the SwiftUI app.
4. SwiftUI views stay decoupled from Python details; they talk only to a Swift client wrapping the XPC connection.
5. The PySide6 app remains fully functional on Windows/Linux against the same `txt_process/core/`.

## Non-goals (v1)

- Mac App Store listing or App Sandbox entitlements.
- Removing Python from the bundle (Approach D in the brainstorm).
- Any changes to the PySide6 UI shell.
- iOS / iPadOS targets, cloud sync, shared mappings.
- Windows/Linux ports of the SwiftUI UI.

## Functional requirements (parity with PySide6 app)

### Document handling

- Load `.txt` (with the existing encoding-fallback behavior in `txt_process/core/io.py`).
- Load `.epub`, including DRM/font-obfuscation detection that rejects encrypted EPUBs at load time (`EpubEncryptedError`).
- Show file metadata in the UI (path, size, type).

### Name extraction

- Small-document mode: when `total_chunks <= begin_scan_chunks`, call the LLM on every chunk in order.
- Large-document mode (phased sampled extraction): Phase 1 seed scan (first `begin_scan_chunks` + every `scan_interval`-th chunk), Phase 2 local scan of skipped chunks, Phase 3 targeted fill of skipped chunks with `<2` known-name hits.
- Streamed progress to the UI: `i / N`, current status ("Waiting 2s…", "Calling model…", "Parsing…", "Done", error), and the running deduped name list.
- Cancellable mid-flight.

### Name editor

- Two-column editable table: column A read-only (original), column B editable (replacement).
- Drop names with `occurrence_count == 0` after extraction/import; do not show them.
- Replacement-name cache + autocomplete in the editable column (parity with current behavior fed by `txt_process/core/name_cache.py`).
- Helpers: filter "edited only," search box, reset row / reset all.

### CSV import

- Import `source,target` rows after a document is loaded.
- Keep only rows whose source has `occurrence_count > 0` in the active document.

### Settings

- Persistent JSON config (same schema and on-disk location as today, via `platformdirs`).
- Fields: `base_url`, `model`, `temperature`, `timeout_seconds`, `max_tokens`, `prompt_template`, `chunk_max_bytes`, `request_interval_seconds`, `begin_scan_chunks`, `scan_interval`, `remember_api_key`, `api_key`.
- API key follows existing rule: persisted plaintext only when `remember_api_key` is true; otherwise session-only.
- Settings sheet/dialog reachable from the main window.

### Normalize Layout

- TXT-only operation (mirrors `txt_process/core/normalize_txt.py`).
- Action surfaced only when a `.txt` is loaded; hidden for `.epub`.

### Replace / export

- Only replace rows with non-empty replacements different from the original.
- Length-descending replacement order.
- Boundary/case-aware matching for ASCII-letter names; exact substring for non-ASCII.
- Output filename: insert `_processed` before the extension; same directory as input; prompt the user for an alternate directory on permission failure.
- EPUB output preserves container structure (chapters, CSS, images, fonts, TOC) byte-for-byte for non-text assets; XHTML/NCX serialized via `lxml-xml` with DOCTYPE re-prepended; zip written directly without going through `ebooklib.write_epub`.

## Invariants that must hold (carried over from `AGENTS.md`)

These are not negotiable in the rebuild — they exist because earlier iterations got them wrong:

- Chunk size: every chunk strictly `< 16 * 1024` bytes (UTF-8).
- Chunk composition: consecutive paragraph groups in original order; oversized-paragraph fallback uses zero-width lookbehind split so inter-sentence whitespace survives reassembly.
- LLM calls: serial only; no concurrency.
- Cadence: ≥2.0 seconds between request *starts* (monotonic clock), including the corrective-retry path.
- Endpoint routing: `base_url` on port `11434` → Ollama native `/api/chat`; otherwise OpenAI-compatible `chat.completions`. API key may be empty for Ollama.
- Parse contract: strict JSON `{"names": [...]}`; one corrective retry with a stricter instruction on parse failure; no heuristic line-by-line fallback; if the retry still fails, surface the `ValueError` as a chunk failure.
- Occurrence counting and replacement matching share a single implementation: `core.replace.count_name_occurrences`.
- API key never logged, echoed, or surfaced in error dialogs.

## Architectural shape (high-level, not a plan)

- `Renamr.app/Contents/MacOS/Renamr` — SwiftUI front-end.
- `Renamr.app/Contents/XPCServices/RenamrPythonService.xpc` — embedded Python interpreter, calls `txt_process/core/` directly.
- A Swift `RenamrService` client wraps `NSXPCConnection` and exposes `async` methods to SwiftUI views (`loadDocument`, `extractNames`, `commitNamePairs`, `replaceAndExport`, `readSettings`, `writeSettings`, `normalizeLayout`, `cancel`).
- Progress events stream from the XPC service to the client (mechanism — reply blocks vs `AsyncSequence` — is a planning decision).
- The client handles connection lifecycle: invalidation → auto-restart of the XPC service; per-call timeouts; cancellation propagated to the Python side.
- The Python side is a thin adapter that exposes `core/` functions over the bridge protocol. Orchestration that currently lives in `txt_process/ui/workers.py` (chunking driver, cadence enforcement, phased-extraction state machine) is reshaped during planning — see Open Questions.

## Scope boundaries

### Deferred for later

- Mac App Store listing; revisit only if distribution goals change.
- Approach D (port `core/` to Swift, drop Python from the bundle); revisit only if the parallel-maintenance cost of two UIs against one Python core proves unbearable.
- Windows/Linux versions of the SwiftUI UI; PySide6 stays as the cross-platform path.

### Outside this product's identity

- iOS / iPadOS targets.
- Cloud sync, account systems, or shared mapping libraries.
- A web UI.

## Dependencies / assumptions

- macOS 14 (Sonoma) minimum target — current SwiftUI features and `NSXPCConnection` async ergonomics rely on this baseline. (Confirm at planning time.)
- Developer ID Application certificate and a notarization API key are available to whoever builds release artifacts.
- A bundleable Python distribution exists that can host the current `core/` dependencies (lxml, ebooklib, httpx, the OpenAI SDK). BeeWare's `python-apple-support` is the strong candidate; not yet verified end-to-end against this dependency set.
- `txt_process/core/` is already UI-agnostic; the rebuild does not require breaking changes to its public surface. The Qt-coupled orchestration in `txt_process/ui/workers.py` is *not* assumed reusable as-is.

## Open questions (for `ce-plan`)

1. **Python distribution** — BeeWare's `python-apple-support` xcframework, python.org `Python.framework`, or a custom stripped build? Trade-off is bundle size vs. update cadence vs. ease of including native deps (lxml).
2. **Bridge protocol shape** — NSXPC `@objc` protocol with Foundation types, or `Codable` messages over `NSXPCConnection`'s remote-object plumbing? Driven by ergonomics for rich payloads (name-pair lists with per-name counts).
3. **Progress reporting style** — XPC reply blocks plus a delegate callback, vs. an `AsyncSequence`-shaped progress stream consumed directly by SwiftUI views.
4. **Orchestration relocation** — does the chunking driver / cadence enforcement / phased-extraction state machine move *into* `core/` (so the PySide6 UI can also drop it from `ui/workers.py`) or get re-implemented Swift-side? The first option compounds value; the second is faster for the pilot.
5. **Shared-test strategy** — how do we enforce "every future `core/` change keeps both UIs working"? Candidate: a scenario harness in `tests/` that exercises the same fixtures through both bridges (or at least through the `core/` API both bridges call).
6. **Bundle-size target** — concrete number to commit to in Success Criteria (currently expressed as "meaningfully smaller than 150-200MB").
7. **Updater choice** — Sparkle (mature, well-known) vs. a smaller hand-rolled checker vs. delegating to a distribution channel like Homebrew Cask.

## Success criteria

- `Renamr.app` opens, loads a `.txt` and an `.epub`, runs end-to-end extraction → edit → replace/export on both, and produces output identical (byte-for-byte for non-text EPUB assets; text content semantically equivalent) to what the PySide6 build produces from the same input + settings.
- All Renamr invariants pass a parity test suite that runs against both UIs (or at least against the `core/` calls both UIs make).
- Killing the XPC service mid-extraction (via `kill`) does not crash the SwiftUI app; the UI surfaces a recoverable error and the user can retry.
- Bundle size for the signed `.app` is **meaningfully smaller** than the current PyInstaller build (concrete number pinned in planning — see Open Question 6).
- Cold-launch time on Apple Silicon is no worse than the current PyInstaller build (and ideally noticeably better).
- Codesigning + notarization + `.dmg` packaging runs as a single scripted command.
- Auto-update successfully delivers a point release from a hosted appcast on a developer machine.

## Accepted trade-offs (named explicitly)

- **Two UIs forever.** Parallel long-term means every future business-logic change has to be exercised against both the PySide6 and SwiftUI shells. We accept this in exchange for keeping Windows/Linux users on a single supported app. The shared-test strategy (Open Question 5) is how we keep the cost down.
- **Python stays in the bundle.** The `.app` will still carry Python.framework + stdlib + lxml + ebooklib + the LLM client deps (~50-80MB realistic). This is smaller than the Qt-based bundle but is not "Swift-only small." If Approach D ever becomes attractive, this trade-off is the trigger to revisit.
- **XPC plumbing up front.** The pilot is slower to first runnable build than an in-process PythonKit prototype would be. We pay this cost once to get process isolation and a sandbox-ready foundation, instead of rebuilding the bridge later.

## Handoff

This document is the input to `ce-plan`. Planning should resolve the seven Open Questions above and produce a concrete sequence of tracks (e.g., embedding-mechanics spike, bridge protocol, Swift coordinator, SwiftUI surfaces in parity order, packaging pipeline, parity test harness).
