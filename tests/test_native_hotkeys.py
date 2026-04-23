"""native_hotkeys helpers (no pynput required for unit tests)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from TTS_ka.native_hotkeys import (
    clipboard_tts_argv,
    default_hotkey_callbacks,
    resolved_hotkey_lang_map,
    spawn_clipboard_tts,
)


def test_clipboard_tts_argv() -> None:
    argv = clipboard_tts_argv("ka-m")
    assert argv[-2:] == ["--lang", "ka-m"]
    assert "TTS_ka" in argv


def test_spawn_clipboard_tts_popen(monkeypatch) -> None:
    seen: list = []

    def fake_popen(args, **kwargs):
        seen.append((args, kwargs))
        return None

    monkeypatch.setattr("TTS_ka.native_hotkeys.subprocess.Popen", fake_popen)
    spawn_clipboard_tts("ru")
    assert len(seen) == 1
    assert seen[0][0][-2:] == ["--lang", "ru"]


def test_resolved_hotkey_lang_map_override_and_null_removes() -> None:
    cfg = {
        "hotkeys": {
            "<ctrl>+<alt>+9": "ru",
            "<ctrl>+<alt>+1": None,
        }
    }
    m = resolved_hotkey_lang_map(cfg)
    assert "<ctrl>+<alt>+1" not in m
    assert m["<ctrl>+<alt>+9"] == "ru"
    assert m["<ctrl>+<alt>+2"] == "ru"
    assert m["<ctrl>+<alt>+3"] == "ka"


def test_native_hotkey_manager_restart_calls_stop_then_start(monkeypatch) -> None:
    from TTS_ka.native_hotkeys import NativeHotkeyManager

    mgr = NativeHotkeyManager()
    calls: list[Any] = []

    def fake_stop() -> None:
        calls.append("stop")

    def fake_start(
        mapping: object = None,
        *,
        config: object = None,
    ) -> bool:
        calls.append(("start", config))
        return True

    monkeypatch.setattr(mgr, "stop", fake_stop)
    monkeypatch.setattr(mgr, "start", fake_start)
    assert mgr.restart(config={"hotkeys": {"<ctrl>+<alt>+9": "en"}}) is True
    assert calls == ["stop", ("start", {"hotkeys": {"<ctrl>+<alt>+9": "en"}})]


def test_default_hotkey_callbacks_invoke_spawn(monkeypatch) -> None:
    langs: list[str] = []

    def capture(lang: str) -> None:
        langs.append(lang)

    monkeypatch.setattr("TTS_ka.native_hotkeys.spawn_clipboard_tts", capture)
    cbs = default_hotkey_callbacks()
    for _combo, fn in cbs.items():
        fn()
    assert set(langs) == {"en", "ka", "ka-m", "ru"}
