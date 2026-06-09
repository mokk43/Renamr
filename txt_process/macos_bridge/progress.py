"""Progress payload helpers for the macOS bridge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class BridgeProgressEvent:
    """Serializable progress event emitted to the Swift host."""

    stage: str
    current: int
    total: int
    detail: str | None
    running_names: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable payload."""
        return {
            "stage": self.stage,
            "current": self.current,
            "total": self.total,
            "detail": self.detail,
            "running_names": self.running_names,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BridgeProgressEvent:
        """Construct from a decoded JSON dict."""
        return cls(
            stage=str(payload.get("stage", "")),
            current=int(payload.get("current", 0)),
            total=int(payload.get("total", 0)),
            detail=str(payload["detail"]) if payload.get("detail") is not None else None,
            running_names=[str(item) for item in payload.get("running_names", [])],
        )
