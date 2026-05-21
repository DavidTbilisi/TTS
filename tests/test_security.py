"""BUG-4: ensure no shell injection via os.system in package code."""

from __future__ import annotations

import ast
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PKG_ROOT = Path(__file__).resolve().parent.parent / "src" / "TTS_ka"


def _find_os_system_calls(source: str) -> list[int]:
    """Return the line numbers of any `os.system(...)` calls in *source*."""
    tree = ast.parse(source)
    hits: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            attr = node.func
            if (
                attr.attr == "system"
                and isinstance(attr.value, ast.Name)
                and attr.value.id == "os"
            ):
                hits.append(node.lineno)
    return hits


def test_no_os_system_calls_in_package():
    """Static guarantee: zero `os.system(...)` calls anywhere under src/TTS_ka/."""
    offending: list[tuple[Path, list[int]]] = []
    for path in PKG_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        hits = _find_os_system_calls(source)
        if hits:
            offending.append((path, hits))
    assert offending == [], (
        f"os.system(...) calls found (BUG-4): "
        + ", ".join(f"{p}:{lines}" for p, lines in offending)
    )


class TestPlayAudioSafety:
    """`play_audio` must not invoke a shell on non-Windows platforms."""

    def test_play_audio_uses_subprocess_list_form_on_linux(self):
        """On Linux, play_audio launches mpv (or fallback) via subprocess.Popen with shell=False."""
        from TTS_ka import fast_audio
        with patch.object(fast_audio.sys, "platform", "linux"), \
             patch.object(fast_audio.shutil, "which", return_value="/usr/bin/mpv"), \
             patch.object(fast_audio.subprocess, "Popen") as mpopen:
            fast_audio.play_audio("/tmp/a'b.mp3")
        mpopen.assert_called_once()
        call_args, call_kwargs = mpopen.call_args
        assert isinstance(call_args[0], list), "argv must be a list, not a shell string"
        assert call_args[0] == ["mpv", os.path.abspath("/tmp/a'b.mp3")]
        assert call_kwargs.get("shell", False) is False

    def test_play_audio_uses_subprocess_list_form_on_darwin(self):
        """On macOS, play_audio launches `open` via subprocess.Popen list-form."""
        from TTS_ka import fast_audio
        with patch.object(fast_audio.sys, "platform", "darwin"), \
             patch.object(fast_audio.subprocess, "Popen") as mpopen:
            fast_audio.play_audio("/tmp/Hello World.mp3")
        mpopen.assert_called_once()
        call_args, call_kwargs = mpopen.call_args
        assert call_args[0] == ["open", os.path.abspath("/tmp/Hello World.mp3")]
        assert call_kwargs.get("shell", False) is False

    def test_play_audio_handles_quote_in_filename(self):
        """A filename with a single quote does not error or escape the args list."""
        from TTS_ka import fast_audio
        with patch.object(fast_audio.sys, "platform", "linux"), \
             patch.object(fast_audio.shutil, "which", return_value="/usr/bin/mpv"), \
             patch.object(fast_audio.subprocess, "Popen") as mpopen:
            fast_audio.play_audio("/tmp/Liam O'Brien.mp3")
        # Single quote stays in the filename as a literal arg
        argv = mpopen.call_args.args[0]
        assert argv[1] == os.path.abspath("/tmp/Liam O'Brien.mp3")


class TestFFmpegMergerSafety:
    """`FFmpegMerger.merge` must invoke ffmpeg via subprocess argv, not a shell string."""

    def test_ffmpeg_merger_uses_argv_not_shell_string(self, tmp_path):
        """ffmpeg is called via subprocess.run with a list and shell=False."""
        from TTS_ka import fast_audio
        # Create dummy part files so os.path.exists checks pass
        part1 = tmp_path / "a.mp3"
        part2 = tmp_path / "b.mp3"
        part1.write_bytes(b"\x00")
        part2.write_bytes(b"\x00")
        merger = fast_audio.FFmpegMerger()
        with patch.object(fast_audio.subprocess, "run") as mrun:
            mrun.return_value = MagicMock(returncode=0)
            merger.merge([str(part1), str(part2)], str(tmp_path / "out.mp3"))
        mrun.assert_called_once()
        call_args, call_kwargs = mrun.call_args
        argv = call_args[0]
        assert isinstance(argv, list)
        assert argv[0] == "ffmpeg"
        assert call_kwargs.get("shell", False) is False

    def test_ffmpeg_merger_escapes_single_quotes_in_concat_listfile(self, tmp_path):
        """Filenames with single quotes are escaped per ffmpeg concat-demuxer spec."""
        from TTS_ka import fast_audio
        part = tmp_path / "Liam O'Brien.mp3"
        part.write_bytes(b"\x00")
        captured: dict[str, str] = {}

        def fake_run(argv, **_kwargs):
            # Capture the concat listfile content as ffmpeg would see it
            with open(argv[argv.index("-i") + 1], encoding="utf-8") as f:
                captured["content"] = f.read()
            return MagicMock(returncode=0)

        merger = fast_audio.FFmpegMerger()
        with patch.object(fast_audio.subprocess, "run", side_effect=fake_run):
            merger.merge([str(part), str(part)], str(tmp_path / "out.mp3"))
        # ffmpeg's concat-demuxer escape for `'` is `'\''`
        assert "O'\\''Brien" in captured["content"]

    def test_ffmpeg_missing_falls_back_to_copy(self, tmp_path):
        """If ffmpeg is not installed, the first part is copied as a fallback."""
        from TTS_ka import fast_audio
        part1 = tmp_path / "a.mp3"
        part2 = tmp_path / "b.mp3"
        part1.write_bytes(b"PART1")
        part2.write_bytes(b"PART2")
        out = tmp_path / "out.mp3"
        merger = fast_audio.FFmpegMerger()
        with patch.object(fast_audio.subprocess, "run", side_effect=FileNotFoundError):
            merger.merge([str(part1), str(part2)], str(out))
        assert out.read_bytes() == b"PART1"


class TestStreamingPlayerUnixFallbackSafety:
    """`StreamingAudioPlayer._unix_fallback` must use subprocess (not os.system)."""

    def test_unix_fallback_uses_subprocess(self):
        """Drain queue then spawn afplay/mpg123 via subprocess.Popen list-form."""
        from TTS_ka import streaming_player as sp
        player = sp.StreamingAudioPlayer(show_gui=False)
        player.chunk_queue.put("/tmp/chunk.mp3")
        player.chunk_queue.put(None)
        with patch.object(sp.sys, "platform", "linux"), \
             patch.object(sp, "subprocess") as msp:
            msp.DEVNULL = -3
            player._unix_fallback()
        msp.Popen.assert_called_once()
        call_args, call_kwargs = msp.Popen.call_args
        argv = call_args[0]
        assert isinstance(argv, list)
        assert argv[0] == "mpg123"
        # Path is run through os.path.abspath, so it may be absolutized on Windows.
        # The key invariant is that the chunk file name reaches subprocess as a
        # literal argv element with no shell quoting.
        assert argv[1].replace("\\", "/").endswith("chunk.mp3")
        assert call_kwargs.get("shell", False) is False
        assert call_kwargs.get("start_new_session") is True
