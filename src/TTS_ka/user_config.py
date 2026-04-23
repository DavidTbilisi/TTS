"""Load optional JSON user preferences (language, speed, playback, HTTP behavior)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Mapping

LANG_CODES = frozenset({"ka", "ka-m", "ru", "en"})


def merge_hotkey_bindings(
    cfg: Mapping[str, Any],
    defaults: Mapping[str, str],
) -> dict[str, str]:
    """Merge optional ``cfg["hotkeys"]`` onto *defaults* (pynput combo string -> ``--lang``).

    Values must be one of ``ka``, ``ka-m``, ``ru``, ``en``. JSON ``null`` removes that combo
    from the effective map (including overriding a default).
    """
    merged = dict(defaults)
    hm = cfg.get("hotkeys")
    if not isinstance(hm, dict):
        return merged
    for k, v in hm.items():
        if not isinstance(k, str):
            continue
        key = k.strip()
        if not key:
            continue
        if v is None:
            merged.pop(key, None)
            continue
        if isinstance(v, str):
            lang = v.strip()
            if lang in LANG_CODES:
                merged[key] = lang
    return merged


def default_config_path() -> Path:
    """Default file: ``~/.tts_config.json`` (same path documented in the readme)."""
    return Path.home() / ".tts_config.json"


def resolve_config_path(explicit: str | None) -> Path | None:
    """Pick config path: CLI ``--config``, then ``TTS_KA_CONFIG``, then default if it exists."""
    if explicit and explicit.strip():
        return Path(os.path.expanduser(explicit.strip()))
    env = os.environ.get("TTS_KA_CONFIG", "").strip()
    if env:
        return Path(os.path.expanduser(env))
    p = default_config_path()
    return p if p.is_file() else None


def load_user_config(explicit: str | None = None) -> Dict[str, Any]:
    """Parse JSON object from disk; return ``{}`` if missing or invalid."""
    path = resolve_config_path(explicit)
    if path is None or not path.is_file():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def write_user_config(path: str | os.PathLike[str], data: Mapping[str, Any]) -> None:
    """Write *data* as UTF-8 JSON to *path* (parent directories are created)."""
    p = Path(os.path.expanduser(os.fspath(path)))
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def apply_env_from_config(cfg: Mapping[str, Any]) -> None:
    """Apply ``skip_http`` / ``verbose`` / ``vlc_rc`` to the process environment if not already set."""
    if not cfg:
        return

    def set_if_unset(key: str, val: str) -> None:
        if os.environ.get(key, "").strip():
            return
        os.environ[key] = val

    if cfg.get("skip_http"):
        set_if_unset("TTS_KA_SKIP_HTTP", "1")
    if cfg.get("verbose"):
        set_if_unset("TTS_KA_VERBOSE", "1")
    if cfg.get("vlc_rc") is False:
        set_if_unset("TTS_KA_VLC_RC", "0")


def _as_bool(val: Any, default: bool = False) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "yes", "on")
    return default


def _as_int(val: Any, default: int = 0) -> int:
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def argparse_defaults_from_config(cfg: Mapping[str, Any]) -> Dict[str, Any]:
    """Defaults for the main CLI parser (positional options + config-driven flags)."""
    lang = cfg.get("lang", "en")
    if not isinstance(lang, str) or lang not in LANG_CODES:
        lang = "en"
    out = cfg.get("output", "data.mp3")
    if not isinstance(out, str) or not out.strip():
        out = "data.mp3"
    return {
        "lang": lang,
        "chunk_seconds": max(0, _as_int(cfg.get("chunk_seconds"), 0)),
        "parallel": max(0, _as_int(cfg.get("parallel"), 0)),
        "output": out.strip(),
        "no_play": _as_bool(cfg.get("no_play"), False),
        "stream": _as_bool(cfg.get("stream"), False),
        "no_turbo": _as_bool(cfg.get("no_turbo", cfg.get("legacy")), False),
        "no_gui": _as_bool(cfg.get("no_gui", cfg.get("streaming_headless")), False),
    }


def resolved_playback_flags(args: Any, defaults: Mapping[str, Any]) -> Dict[str, Any]:
    """Merge ``argparse.SUPPRESS`` booleans: explicit CLI flags win over config defaults."""
    no_play = True if getattr(args, "no_play", None) is True else bool(defaults.get("no_play", False))
    stream = True if getattr(args, "stream", None) is True else bool(defaults.get("stream", False))
    no_turbo = True if getattr(args, "no_turbo", None) is True else bool(defaults.get("no_turbo", False))
    no_gui = True if getattr(args, "no_gui", None) is True else bool(defaults.get("no_gui", False))
    return {
        "no_play": no_play,
        "stream": stream,
        "no_turbo": no_turbo,
        "no_gui": no_gui,
        "show_player": not no_gui,
    }
