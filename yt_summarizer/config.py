"""User configuration and stable application paths."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from platformdirs import user_cache_path, user_config_path, user_data_path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib


def config_path() -> Path:
    if root := os.environ.get("XDG_CONFIG_HOME"):
        return Path(root) / "yt-summarizer" / "config.toml"
    return user_config_path("yt-summarizer", appauthor=False) / "config.toml"


def default_cache_dir() -> str:
    if root := os.environ.get("XDG_CACHE_HOME"):
        return str(Path(root) / "yt-summarizer")
    return str(user_cache_path("yt-summarizer", appauthor=False))


def default_output_dir() -> str:
    if root := os.environ.get("XDG_DATA_HOME"):
        return str(Path(root) / "yt-summarizer" / "summaries")
    return str(user_data_path("yt-summarizer", appauthor=False) / "summaries")


def load(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    selected = Path(path).expanduser() if path else config_path()
    if not selected.is_file():
        return {}
    try:
        with selected.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"Could not read config {selected}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Config {selected} must contain a TOML table")
    return data


def presets(data: dict[str, Any]) -> dict[str, str]:
    configured = data.get("presets", {})
    if not isinstance(configured, dict):
        raise ValueError("Config [presets] must be a TOML table")
    return {str(name): str(prompt) for name, prompt in configured.items()}


def setting(data: dict[str, Any], key: str, default: Any) -> Any:
    value = data.get(key, default)
    return os.path.expanduser(value) if isinstance(value, str) else value
