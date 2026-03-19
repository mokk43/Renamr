"""Configuration management with persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import platformdirs

APP_NAME = "Renamr"
CONFIG_FILE = "config.json"

# Default extraction prompt template
DEFAULT_PROMPT_TEMPLATE = """You are a character name extractor. Given the following text excerpt, identify all character names (people's names, nicknames, titles used as names).

Rules:
- Only extract names of people/characters, not places or organizations
- Include full names, nicknames, and titles used to address characters
- Do not include generic titles like "先生" or "老师" unless they are part of a specific character's name
- Remove duplicates
- Output ONLY valid JSON in this exact format: {"names": ["Name1", "Name2", ...]}

Text:
{chunk_text}

Output only the JSON, nothing else:"""


@dataclass
class Config:
    """Application configuration."""

    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = 0.1
    timeout_seconds: float = 60.0
    max_tokens: int | None = None
    prompt_template: str = field(default_factory=lambda: DEFAULT_PROMPT_TEMPLATE)
    chunk_max_bytes: int = 16384
    request_interval_seconds: float = 2.0
    remember_api_key: bool = False
    api_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        """Create config from dictionary."""
        # Filter only known fields
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


def get_config_dir() -> Path:
    """Get the user config directory for this app."""
    return Path(platformdirs.user_config_dir(APP_NAME))


def get_config_path() -> Path:
    """Get the full path to the config file."""
    return get_config_dir() / CONFIG_FILE


def load_config() -> Config:
    """Load configuration from disk, or return defaults if not found."""
    config_path = get_config_path()
    if config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
            return Config.from_dict(data)
        except (json.JSONDecodeError, OSError):
            pass
    return Config()


def save_config(config: Config) -> None:
    """Save configuration to disk."""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = get_config_path()
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)


