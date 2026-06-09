"""Python dispatcher used by the macOS XPC host."""

from __future__ import annotations

import json
import logging
import platform
import re
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from txt_process.core import api
from txt_process.core.config import Config
from txt_process.core.epub_io import EpubEncryptedError, EpubParseError
from txt_process.core.extraction import ExtractionCallbacks, ExtractionCancelled, ProgressEvent

from .progress import BridgeProgressEvent

_LOG = logging.getLogger("txt_process.macos_bridge")
_CANCEL_EVENTS: dict[str, threading.Event] = {}
_CANCEL_LOCK = threading.Lock()

_SENSITIVE_PATTERNS = [
    re.compile(r"Authorization:\s*[^\s]+", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_\-]+\b"),
]
ProgressCallback = Callable[[str], None]


def _sanitize_message(message: str) -> str:
    sanitized = message
    for pattern in _SENSITIVE_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


def _ok_response(result: Any) -> str:
    return json.dumps({"ok": True, "result": result}, ensure_ascii=False)


def _error_response(code: str, message: str) -> str:
    return json.dumps(
        {"ok": False, "error": code, "message": _sanitize_message(message)},
        ensure_ascii=False,
    )


def _decode_payload(payload_json: str) -> dict[str, Any]:
    if not payload_json.strip():
        return {}
    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        raise ValueError("Payload must be a JSON object.")
    return payload


def _event_for_token(token: str) -> threading.Event:
    with _CANCEL_LOCK:
        event = _CANCEL_EVENTS.get(token)
        if event is None:
            event = threading.Event()
            _CANCEL_EVENTS[token] = event
        return event


def _clear_token(token: str) -> None:
    with _CANCEL_LOCK:
        _CANCEL_EVENTS.pop(token, None)


def _serialize_document(document) -> dict[str, Any]:
    return {
        "path": str(document.path),
        "kind": document.kind,
        "text": document.text,
        "display_info": document.display_info,
        "supports_normalize": document.supports_normalize,
        "encoding": document.encoding,
    }


def _serialize_extraction_result(result) -> dict[str, Any]:
    return {
        "name_pairs": [[name, replacement] for name, replacement in result.name_pairs],
        "counts": result.counts,
        "errors": result.errors,
    }


def _serialize_replace_result(result) -> dict[str, Any]:
    return {
        "output_path": str(result.output_path),
        "totals": result.totals,
        "per_item": result.per_item or {},
    }


def _coerce_pairs(raw_pairs: Any) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if not isinstance(raw_pairs, list):
        return pairs
    for item in raw_pairs:
        if not isinstance(item, list | tuple) or len(item) < 2:
            continue
        source = str(item[0]).strip()
        target = str(item[1]).strip()
        if source:
            pairs.append((source, target))
    return pairs


def _coerce_mappings(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    mappings: dict[str, str] = {}
    for key, value in raw.items():
        source = str(key).strip()
        target = str(value).strip()
        if source:
            mappings[source] = target
    return mappings


def _emit_event(
    callback: ProgressCallback | None, event_type: str, payload: dict[str, Any]
) -> None:
    if callback is None:
        return
    envelope = {"type": event_type, "payload": payload}
    message = json.dumps(envelope, ensure_ascii=False)
    try:
        callback(message)
    except Exception:  # noqa: BLE001
        _LOG.exception("Progress callback failed")


class _BridgeCallbacks(ExtractionCallbacks):
    def __init__(self, *, progress_callback: ProgressCallback | None, token: str | None) -> None:
        self._progress_callback = progress_callback
        self._token = token

    def on_progress(self, event: ProgressEvent) -> None:
        payload = BridgeProgressEvent(
            stage=event.stage,
            current=event.current,
            total=event.total,
            detail=event.detail,
            running_names=event.running_names,
        ).to_dict()
        _emit_event(self._progress_callback, "progress", payload)

    def on_log(self, message: str) -> None:
        _emit_event(
            self._progress_callback,
            "log",
            {"level": "info", "message": _sanitize_message(message)},
        )

    def on_chunk_names(self, chunk_index: int, names: list[str]) -> None:
        _emit_event(
            self._progress_callback,
            "chunk_names",
            {"chunk_index": chunk_index, "names": names},
        )

    def on_chunk_error(self, chunk_index: int, message: str) -> None:
        _emit_event(
            self._progress_callback,
            "chunk_error",
            {"chunk_index": chunk_index, "message": _sanitize_message(message)},
        )

    def should_cancel(self) -> bool:
        if not self._token:
            return False
        return _event_for_token(self._token).is_set()


def _method_ping(_: dict[str, Any]) -> dict[str, Any]:
    return {"python_version": platform.python_version()}


def _method_cancel(payload: dict[str, Any], token: str | None) -> dict[str, Any]:
    resolved_token = token or str(payload.get("token", "")).strip()
    if not resolved_token:
        return {"cancelled": False}
    _event_for_token(resolved_token).set()
    return {"cancelled": True, "token": resolved_token}


def _method_load_document(payload: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(payload["path"]))
    document = api.load_document(path)
    return _serialize_document(document)


def _method_extract_names(
    payload: dict[str, Any],
    progress_callback: ProgressCallback | None,
    token: str | None,
) -> dict[str, Any]:
    path = Path(str(payload["documentPath"]))
    document = api.load_document(path)

    config_dict = payload.get("config", {})
    if not isinstance(config_dict, dict):
        raise ValueError("config must be a JSON object")
    config = Config.from_dict(config_dict)

    provided_key = str(payload.get("api_key", "")).strip()
    api_key = provided_key or config.api_key
    callbacks = _BridgeCallbacks(progress_callback=progress_callback, token=token)
    try:
        result = api.extract_names(
            document.text, config=config, api_key=api_key, callbacks=callbacks
        )
    except ExtractionCancelled:
        return {"name_pairs": [], "counts": {}, "errors": ["cancelled"]}
    finally:
        if token:
            _clear_token(token)
    return _serialize_extraction_result(result)


def _method_replace_and_export(payload: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(payload["documentPath"]))
    document = api.load_document(path)
    mappings = _coerce_mappings(payload.get("mappings", {}))
    output_raw = payload.get("outputPath")
    output_path = Path(str(output_raw)) if output_raw else None
    result = api.replace_and_export(document, mappings, output_path=output_path)
    return _serialize_replace_result(result)


def _method_read_settings(_: dict[str, Any]) -> dict[str, Any]:
    config = api.read_settings()
    serialized = config.to_dict()
    serialized["api_key"] = ""
    return serialized


def _method_write_settings(payload: dict[str, Any]) -> dict[str, Any]:
    config_dict = payload.get("config", payload)
    if not isinstance(config_dict, dict):
        raise ValueError("config must be a JSON object")
    config = Config.from_dict(config_dict)
    api.write_settings(config)
    return {"saved": True}


def _method_normalize_layout(payload: dict[str, Any]) -> dict[str, Any]:
    input_path = Path(str(payload["inputPath"]))
    output_path = Path(str(payload["outputPath"]))
    api.normalize_layout(input_path, output_path)
    return {"output_path": str(output_path)}


def _method_load_name_cache(_: dict[str, Any]) -> dict[str, Any]:
    return {"names": api.load_name_cache()}


def _method_save_name_cache(payload: dict[str, Any]) -> dict[str, Any]:
    names = [str(item) for item in payload.get("names", [])]
    stored = api.save_name_cache(names)
    return {"names": stored}


def _method_commit_imported_pairs(payload: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(payload["documentPath"]))
    document = api.load_document(path)
    pairs = _coerce_pairs(payload.get("pairs", []))
    filtered_pairs, counts = api.commit_imported_pairs(document, pairs)
    rows = [
        {
            "original_name": source,
            "replacement_name": target,
            "occurrence_count": counts.get(source, 0),
        }
        for source, target in filtered_pairs
    ]
    return {"rows": rows, "counts": counts}


def dispatch(
    method_name: str,
    payload_json: str,
    progress_callback: ProgressCallback | None = None,
    token: str | None = None,
) -> str:
    """Dispatch one XPC-style request and return a JSON-encoded response."""
    try:
        payload = _decode_payload(payload_json)
    except json.JSONDecodeError as exc:
        return _error_response("pythonRaised", f"Invalid JSON payload: {exc.msg}")
    except ValueError as exc:
        return _error_response("pythonRaised", str(exc))

    try:
        if method_name == "ping":
            return _ok_response(_method_ping(payload))
        if method_name == "cancel":
            return _ok_response(_method_cancel(payload, token))
        if method_name == "loadDocument":
            return _ok_response(_method_load_document(payload))
        if method_name == "extractNames":
            return _ok_response(_method_extract_names(payload, progress_callback, token))
        if method_name == "replaceAndExport":
            return _ok_response(_method_replace_and_export(payload))
        if method_name == "readSettings":
            return _ok_response(_method_read_settings(payload))
        if method_name == "writeSettings":
            return _ok_response(_method_write_settings(payload))
        if method_name == "normalizeLayout":
            return _ok_response(_method_normalize_layout(payload))
        if method_name == "loadNameCache":
            return _ok_response(_method_load_name_cache(payload))
        if method_name == "saveNameCache":
            return _ok_response(_method_save_name_cache(payload))
        if method_name == "commitImportedPairs":
            return _ok_response(_method_commit_imported_pairs(payload))
        return _error_response("pythonRaised", f"Unknown method: {method_name}")
    except FileNotFoundError as exc:
        return _error_response("documentNotFound", str(exc))
    except EpubEncryptedError as exc:
        return _error_response("documentEncrypted", str(exc))
    except EpubParseError as exc:
        return _error_response("epubParseFailed", str(exc))
    except PermissionError as exc:
        return _error_response("permissionDenied", str(exc))
    except ValueError as exc:
        return _error_response("llmConfigInvalid", str(exc))
    except ExtractionCancelled:
        return _error_response("cancelled", "cancelled")
    except Exception as exc:  # noqa: BLE001
        _LOG.exception("Unhandled bridge error in %s", method_name)
        return _error_response("pythonRaised", str(exc))
