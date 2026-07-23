"""Tests for TTS_ka.deps."""

from __future__ import annotations

import os
from unittest.mock import patch

from TTS_ka.deps import (
    DepRow,
    check_clipboard,
    check_ffmpeg,
    format_dep_report,
    run_dependency_check,
)


def _which(*present: str):
    """shutil.which stub: only *present* executables resolve."""
    return lambda cmd: f"/usr/bin/{cmd}" if cmd in present else None


def test_format_dep_report_smoke() -> None:
    rows = [
        DepRow("edge-tts", True, "ok"),
        DepRow("ffmpeg", True, "ffmpeg version 6"),
    ]
    text = format_dep_report(rows)
    assert "edge-tts" in text
    assert "ffmpeg" in text
    assert "[OK]" in text


def test_format_dep_report_shows_fix_for_failing_row() -> None:
    rows = [
        DepRow("edge-tts", True, "ok"),
        DepRow("pydub", True, "ok"),
        DepRow("ffmpeg", False, "not on PATH", fix="winget install Gyan.FFmpeg"),
    ]
    text = format_dep_report(rows)
    assert "fix: winget install Gyan.FFmpeg" in text


def test_format_dep_report_success_closer() -> None:
    rows = [
        DepRow("edge-tts", True, "ok"),
        DepRow("pydub", True, "ok"),
        DepRow("ffmpeg", True, "ok"),
    ]
    text = format_dep_report(rows)
    assert "All set" in text


def test_check_ffmpeg_missing_populates_fix() -> None:
    with patch("TTS_ka.deps.shutil.which", return_value=None):
        row = check_ffmpeg()
    assert not row.ok
    assert row.fix  # a platform-specific install command is present


class TestCheckClipboard:
    """`cb` needs a session clipboard helper on Linux; OS-native elsewhere."""

    def test_wayland_with_wl_paste_is_ok(self) -> None:
        with patch("TTS_ka.deps.sys.platform", "linux"), \
             patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}), \
             patch("TTS_ka.deps.shutil.which", _which("wl-paste", "xclip")):
            row = check_clipboard()
        assert row.ok
        assert "wl-paste" in row.detail

    def test_wayland_with_only_x11_helper_warns_about_stale_selection(self) -> None:
        with patch("TTS_ka.deps.sys.platform", "linux"), \
             patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}), \
             patch("TTS_ka.deps.shutil.which", _which("xsel")):
            row = check_clipboard()
        assert not row.ok
        assert "stale" in row.detail
        assert "wl-clipboard" in row.fix

    def test_x11_with_xclip_is_ok(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "WAYLAND_DISPLAY"}
        with patch("TTS_ka.deps.sys.platform", "linux"), \
             patch.dict(os.environ, env, clear=True), \
             patch("TTS_ka.deps.shutil.which", _which("xclip")):
            row = check_clipboard()
        assert row.ok
        assert "xclip" in row.detail

    def test_no_helper_reports_fix(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "WAYLAND_DISPLAY"}
        with patch("TTS_ka.deps.sys.platform", "linux"), \
             patch.dict(os.environ, env, clear=True), \
             patch("TTS_ka.deps.shutil.which", _which()):
            row = check_clipboard()
        assert not row.ok
        assert row.fix

    def test_windows_and_macos_are_built_in(self) -> None:
        for platform in ("win32", "darwin"):
            with patch("TTS_ka.deps.sys.platform", platform), \
                 patch("TTS_ka.deps.shutil.which", _which()):
                row = check_clipboard()
            assert row.ok, platform

    def test_clipboard_row_is_optional_not_critical(self) -> None:
        """A missing clipboard helper must not fail the whole doctor run."""
        rows = [
            DepRow("edge-tts", True, "ok"),
            DepRow("pydub", True, "ok"),
            DepRow("ffmpeg", True, "ok"),
            DepRow("clipboard", False, "no wl-paste / xclip / xsel"),
        ]
        text = format_dep_report(rows)
        assert "[opt]" in text
        with patch("TTS_ka.deps.collect_dep_rows", return_value=rows):
            assert run_dependency_check() == 0


@patch("TTS_ka.deps.collect_dep_rows")
def test_run_dependency_check_success(mock_collect) -> None:
    mock_collect.return_value = [
        DepRow("edge-tts", True, "ok"),
        DepRow("pydub", True, "ok"),
        DepRow("httpx", True, "ok"),
        DepRow("soundfile", False, "optional"),
        DepRow("uvloop", False, "optional"),
        DepRow("ffmpeg", True, "ok"),
        DepRow("streaming player", False, "none"),
    ]
    assert run_dependency_check() == 0


@patch("TTS_ka.deps.collect_dep_rows")
def test_run_dependency_check_missing_ffmpeg(mock_collect) -> None:
    mock_collect.return_value = [
        DepRow("edge-tts", True, "ok"),
        DepRow("pydub", True, "ok"),
        DepRow("httpx", True, "ok"),
        DepRow("soundfile", False, "optional"),
        DepRow("uvloop", False, "optional"),
        DepRow("ffmpeg", False, "missing"),
        DepRow("streaming player", True, "vlc"),
    ]
    assert run_dependency_check() == 1


@patch("TTS_ka.deps.collect_dep_rows")
def test_run_dependency_check_missing_edge(mock_collect) -> None:
    mock_collect.return_value = [
        DepRow("edge-tts", False, "ImportError"),
        DepRow("pydub", True, "ok"),
        DepRow("httpx", True, "ok"),
        DepRow("soundfile", False, "optional"),
        DepRow("uvloop", False, "optional"),
        DepRow("ffmpeg", True, "ok"),
        DepRow("streaming player", True, "vlc"),
    ]
    assert run_dependency_check() == 1
