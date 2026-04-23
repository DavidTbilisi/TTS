"""native_hotkeys helpers (no pynput required for unit tests)."""

from __future__ import annotations

from unittest.mock import patch

from TTS_ka.native_hotkeys import clipboard_tts_argv, default_hotkey_callbacks, spawn_clipboard_tts


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


def test_default_hotkey_callbacks_invoke_spawn(monkeypatch) -> None:
    langs: list[str] = []

    def capture(lang: str) -> None:
        langs.append(lang)

    monkeypatch.setattr("TTS_ka.native_hotkeys.spawn_clipboard_tts", capture)
    cbs = default_hotkey_callbacks()
    for _combo, fn in cbs.items():
        fn()
    assert set(langs) == {"en", "ka", "ka-m", "ru"}
