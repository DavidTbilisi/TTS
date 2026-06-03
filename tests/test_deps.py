"""Tests for TTS_ka.deps."""

from __future__ import annotations

from unittest.mock import patch

from TTS_ka.deps import (
    DepRow,
    check_ffmpeg,
    format_dep_report,
    run_dependency_check,
)


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
