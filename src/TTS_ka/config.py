"""Layered defaults for TTS_ka.

Precedence (highest first):
    1. CLI flag (handled by argparse — this module does not see it).
    2. Environment variable.
    3. JSON config file at $XDG_CONFIG_HOME/TTS_ka/config.json,
       ~/.config/TTS_ka/config.json, or the legacy ~/.tts_config.json.
    4. Built-in default (set by argparse).

Malformed JSON or unknown keys log a warning to stderr but never crash.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

VALID_LANGS = {"ka", "ru", "en"}

# JSON key -> argparse-attribute name. Anything else is "unknown" and warned about.
CONFIG_KEY_MAP: Dict[str, str] = {
    "default_lang": "lang",
    "turbo_mode": "turbo",          # inverted at use site (--no-turbo)
    "chunk_seconds": "chunk_seconds",
    "parallel_workers": "parallel",
    "auto_play": "auto_play",       # inverted at use site (--no-play)
    "output": "output",
    "player": "player",
}

ENV_KEY_MAP: Dict[str, str] = {
    "TTS_DEFAULT_LANG": "lang",
    "TTS_DEFAULT_MODE": "turbo",     # value "turbo" => True, anything else => False
    "TTS_DEFAULT_CHUNK_SECONDS": "chunk_seconds",
    "TTS_DEFAULT_PARALLEL": "parallel",
    "TTS_AUTO_PLAY": "auto_play",
    "TTS_OUTPUT_DIR": "output_dir",  # special: prefix for the default filename
    "TTS_DEFAULT_PLAYER": "player",
}

# Defaults match the pre-config behavior so callers can rely on them as a floor.
BUILTIN_DEFAULTS: Dict[str, Any] = {
    "lang": "en",
    "turbo": True,
    "auto_play": True,
    "chunk_seconds": 0,
    "parallel": 0,
    "output": None,
    "output_dir": None,
    "player": None,
}


def _candidate_paths() -> list[Path]:
    """Return JSON config paths to try, in priority order."""
    paths: list[Path] = []
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        paths.append(Path(xdg) / "TTS_ka" / "config.json")
    home = Path.home()
    paths.append(home / ".config" / "TTS_ka" / "config.json")
    paths.append(home / ".tts_config.json")
    return paths


def _coerce_bool(raw: Any) -> Optional[bool]:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on", "turbo"}
    return None


def _coerce_int(raw: Any) -> Optional[int]:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        try:
            return int(raw.strip())
        except ValueError:
            return None
    return None


def _load_file_settings(paths: list[Path]) -> Dict[str, Any]:
    """Load the first existing config file. Warn on malformed JSON."""
    result: Dict[str, Any] = {}
    for path in paths:
        if not path.is_file():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            print(
                f"Warning: malformed JSON in {path}: {exc}. Using defaults.",
                file=sys.stderr,
            )
            return {}
        except OSError as exc:
            print(
                f"Warning: could not read {path}: {exc}. Using defaults.",
                file=sys.stderr,
            )
            return {}
        if not isinstance(data, dict):
            print(
                f"Warning: {path} must contain a JSON object. Ignoring.",
                file=sys.stderr,
            )
            return {}
        for key, value in data.items():
            mapped = CONFIG_KEY_MAP.get(key)
            if mapped is None:
                print(
                    f"Warning: unknown config key {key!r} in {path}.",
                    file=sys.stderr,
                )
                continue
            result[mapped] = value
        return result
    return result


def _load_env_settings(env: Dict[str, str]) -> Dict[str, Any]:
    """Translate env vars into argparse-attribute keyed dict."""
    result: Dict[str, Any] = {}
    for env_key, mapped in ENV_KEY_MAP.items():
        if env_key not in env:
            continue
        result[mapped] = env[env_key]
    return result


def _coerce(key: str, raw: Any) -> Any:
    """Coerce a raw value (str or json-native) into the expected Python type."""
    if key in {"turbo", "auto_play"}:
        return _coerce_bool(raw)
    if key in {"chunk_seconds", "parallel"}:
        return _coerce_int(raw)
    if key == "lang":
        if isinstance(raw, str) and raw in VALID_LANGS:
            return raw
        return None
    # everything else is a string-ish path/name
    if isinstance(raw, str):
        return raw
    return None


def load_settings(env: Optional[Dict[str, str]] = None,
                  config_paths: Optional[list[Path]] = None) -> Dict[str, Any]:
    """Resolve effective defaults from config file + environment.

    Args:
        env: env-var mapping (defaults to ``os.environ``).
        config_paths: candidate config-file paths (defaults to standard locations).

    Returns:
        Dict keyed by argparse-attribute name. Values are validated and coerced;
        invalid entries are dropped with a stderr warning so the rest still apply.
    """
    env = dict(os.environ) if env is None else env
    paths = _candidate_paths() if config_paths is None else config_paths

    settings: Dict[str, Any] = dict(BUILTIN_DEFAULTS)

    file_layer = _load_file_settings(paths)
    env_layer = _load_env_settings(env)

    for raw_layer, source_label in ((file_layer, "config"), (env_layer, "env")):
        for key, raw in raw_layer.items():
            coerced = _coerce(key, raw)
            if coerced is None:
                print(
                    f"Warning: ignoring invalid {source_label} value for {key!r}: {raw!r}",
                    file=sys.stderr,
                )
                continue
            settings[key] = coerced

    return settings
