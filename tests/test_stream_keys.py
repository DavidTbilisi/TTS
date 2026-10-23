"""Single-key playback controls while the CLI streams."""

from __future__ import annotations

import os
import signal
import sys
import termios
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from TTS_ka.stream_keys import NOT_CONTROLLABLE, KeyControls

pytestmark = pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX terminal")


def _player(controllable: bool = True) -> MagicMock:
    p = MagicMock()
    p.controllable = controllable
    p.pause.return_value = True
    p.resume.return_value = True
    p.skip_current.return_value = True
    p.change_speed.side_effect = lambda d: round(1.0 + d, 2)
    return p


class TestHandle:
    def test_space_toggles_pause_and_resume(self):
        player = _player()
        keys = KeyControls(player)
        assert "paused" in keys.handle(" ")
        assert "resumed" in keys.handle("p")
        player.pause.assert_called_once()
        player.resume.assert_called_once()

    def test_failed_pause_does_not_flip_state(self):
        player = _player()
        player.pause.return_value = False
        keys = KeyControls(player)
        assert keys.handle(" ") is None
        keys.handle(" ")
        player.resume.assert_not_called()

    def test_n_skips(self):
        player = _player()
        assert "next" in KeyControls(player).handle("n")
        player.skip_current.assert_called_once()

    @pytest.mark.parametrize("key, delta", [("+", 0.1), ("=", 0.1), ("-", -0.1), ("_", -0.1)])
    def test_speed_keys(self, key, delta):
        player = _player()
        message = KeyControls(player).handle(key)
        player.change_speed.assert_called_once_with(delta)
        assert f"{1.0 + delta:.1f}×" in message

    def test_unknown_key_is_ignored(self):
        player = _player()
        assert KeyControls(player).handle("x") is None
        player.pause.assert_not_called()

    def test_uncontrollable_player_warns_once(self):
        player = _player(controllable=False)
        keys = KeyControls(player)
        assert keys.handle(" ") == NOT_CONTROLLABLE
        assert keys.handle("n") is None
        player.pause.assert_not_called()
        player.skip_current.assert_not_called()

    def test_q_sends_sigint_like_ctrl_c(self):
        with patch("TTS_ka.stream_keys.os.kill") as kill:
            assert KeyControls(_player(controllable=False)).handle("q") is None
        kill.assert_called_once_with(os.getpid(), signal.SIGINT)


@pytest.fixture
def pty_pair():
    master, slave = os.openpty()
    yield master, os.ttyname(slave)
    os.close(master)
    os.close(slave)


def _wait_for(cond, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return False


class TestTerminal:
    def test_reads_keys_in_cbreak_and_restores(self, pty_pair):
        master, path = pty_pair
        before = termios.tcgetattr(master)
        player = _player()
        with patch("TTS_ka.stream_keys.os.tcgetpgrp", return_value=os.getpgrp()), \
             patch("TTS_ka.stream_keys.cprint"):
            with KeyControls(player, tty_path=path) as keys:
                assert keys.active
                lflag = termios.tcgetattr(master)[3]
                assert not lflag & termios.ICANON and not lflag & termios.ECHO
                os.write(master, b"\x1b[A")  # arrow key: ignored
                os.write(master, b"n")
                assert _wait_for(lambda: player.skip_current.called)
            player.pause.assert_not_called()
        assert termios.tcgetattr(master) == before

    def test_hint_shown_once_player_is_controllable(self, pty_pair):
        _, path = pty_pair
        player = _player(controllable=False)
        with patch("TTS_ka.stream_keys.os.tcgetpgrp", return_value=os.getpgrp()), \
             patch("TTS_ka.stream_keys.cprint") as shown:
            with KeyControls(player, tty_path=path):
                time.sleep(0.3)
                assert not shown.called
                player.controllable = True
                assert _wait_for(lambda: shown.called)
        assert shown.call_count == 1

    def test_background_job_leaves_terminal_alone(self, pty_pair):
        master, path = pty_pair
        before = termios.tcgetattr(master)
        with patch("TTS_ka.stream_keys.os.tcgetpgrp", return_value=os.getpgrp() + 1):
            with KeyControls(_player(), tty_path=path) as keys:
                assert not keys.active
                assert termios.tcgetattr(master) == before

    def test_no_terminal_is_a_no_op(self, tmp_path):
        keys = KeyControls(_player(), tty_path=str(tmp_path / "missing"))
        assert not keys.start().active
        keys.close()
        keys.close()


class TestWiring:
    def _run_main(self, argv):
        with patch("sys.argv", ["TTS_ka", *argv]), \
             patch("TTS_ka.main.smart_generate_long_text", new=AsyncMock()) as smart:
            from TTS_ka.main import main
            main()
        return smart.call_args.kwargs

    def test_stream_turns_keys_on(self):
        assert self._run_main(["hello", "--stream"])["key_controls"] is True

    def test_no_keys_turns_them_off(self):
        assert self._run_main(["hello", "--stream", "--no-keys"])["key_controls"] is False

    def test_live_skips_keys_when_stdin_is_the_terminal(self):
        with patch("sys.argv", ["TTS_ka", "--live"]), \
             patch("sys.stdin") as stdin, \
             patch("TTS_ka.live_stream.live_loop", new=AsyncMock()) as live:
            stdin.isatty.return_value = True
            from TTS_ka.main import main
            main()
        assert live.call_args.kwargs["key_controls"] is False

    async def test_live_loop_closes_controls_after_playback(self, temp_dir):
        from TTS_ka.live_stream import live_loop

        async def reader():
            yield None

        controls = MagicMock()
        with patch("TTS_ka.live_stream.KeyControls") as cls:
            cls.return_value.start.return_value = controls
            await live_loop(input_reader=reader(), player=MagicMock(),
                            tmp_dir=temp_dir, key_controls=True)
        controls.close.assert_called_once()
