"""Tests for the mpv JSON-IPC driver.

``_FakeMpv`` stands in for the mpv process: patched in as ``Popen``, it reads
``--input-ipc-server=<path>`` from argv, listens on that Unix socket, answers
commands like mpv does, and lets each test decide when entries finish.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import threading
import time
from unittest.mock import patch

import pytest

from TTS_ka import mpv_ipc
from TTS_ka.mpv_ipc import MpvIpc, MpvIpcError

pytestmark = pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="needs Unix sockets")


class _FakeMpv:
    """Minimal mpv: a process handle plus an IPC server thread."""

    instances: list = []

    def __init__(self, argv, **_kwargs):
        self.argv = argv
        self.commands: list = []
        self.exited = threading.Event()
        self.answer = True           # False: swallow replies (models a hung mpv)
        self.next_entry = 1
        self._conn = None
        self._lock = threading.Lock()
        sock_path = next(a.split("=", 1)[1] for a in argv if a.startswith("--input-ipc-server="))
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(sock_path)
        self._server.listen(1)
        threading.Thread(target=self._serve, daemon=True).start()
        type(self).instances.append(self)

    # Popen surface
    def poll(self):
        return 0 if self.exited.is_set() else None

    def wait(self, timeout=None):
        if not self.exited.wait(timeout):
            raise subprocess.TimeoutExpired(self.argv, timeout)
        return 0

    def kill(self):
        self.killed = True
        self._exit()

    def terminate(self):
        self._exit()

    # IPC
    def emit(self, msg):
        with self._lock:
            if self._conn is not None:
                self._conn.sendall((json.dumps(msg) + "\n").encode())

    def finish(self, entry_id, reason="eof", idle=True):
        self.emit({"event": "end-file", "reason": reason, "playlist_entry_id": entry_id})
        if idle:
            self.emit({"event": "property-change", "id": 1, "name": "idle-active", "data": True})

    def _exit(self):
        self.exited.set()
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self._conn.close()
                self._conn = None
        self._server.close()

    def _serve(self):
        try:
            conn, _ = self._server.accept()
        except OSError:
            return
        with self._lock:
            self._conn = conn
        for raw in conn.makefile("rb"):
            msg = json.loads(raw)
            cmd = msg["command"]
            self.commands.append(cmd)
            if not self.answer:
                continue
            data = None
            if cmd[0] == "loadfile":
                data = {"playlist_entry_id": self.next_entry}
                self.next_entry += 1
            self.emit({"request_id": msg["request_id"], "error": "success", "data": data})
            if cmd[0] == "observe_property":
                self.emit({"event": "property-change", "id": cmd[1], "name": cmd[2], "data": True})
            elif cmd[0] == "loadfile":
                self.emit({"event": "property-change", "id": 1, "name": "idle-active", "data": False})
            elif cmd[0] == "quit":
                self._exit()
                return


@pytest.fixture
def fake_mpv(tmp_path, monkeypatch):
    # Keep the socket path short: AF_UNIX paths are limited to ~104 bytes.
    short = os.path.join("/tmp", f"ttska-t{os.getpid()}-{time.monotonic_ns() % 10**6}")
    os.makedirs(short)
    monkeypatch.setattr(mpv_ipc.tempfile, "tempdir", short)
    _FakeMpv.instances = []
    with patch("TTS_ka.mpv_ipc.subprocess.Popen", _FakeMpv):
        yield _FakeMpv
    for inst in _FakeMpv.instances:
        inst._exit()
    shutil.rmtree(short, ignore_errors=True)


def _started(**kwargs):
    ipc = MpvIpc("mpv", **kwargs)
    ipc.start(connect_timeout=3)
    return ipc, _FakeMpv.instances[-1]


class TestSupport:
    def test_env_flag_disables(self, monkeypatch):
        monkeypatch.setenv("TTS_KA_MPV_IPC", "0")
        assert mpv_ipc.ipc_supported() is False

    def test_enabled_on_posix(self, monkeypatch):
        monkeypatch.setenv("TTS_KA_MPV_IPC", "1")
        assert mpv_ipc.ipc_supported() is (os.name == "posix")


class TestArgv:
    def test_headless_is_audio_only_and_idles(self):
        argv = MpvIpc("mpv").argv("/tmp/x.sock")
        assert "--idle=yes" in argv and "--no-video" in argv
        assert "--player-operation-mode=cplayer" in argv
        assert "--input-ipc-server=/tmp/x.sock" in argv
        assert "--playlist=-" not in argv

    def test_never_matches_the_stdin_playlist_invocation(self):
        """User mpv wrappers key on --playlist=- / --keep-open for the GUI path."""
        argv = MpvIpc("mpv").argv("/tmp/x.sock")
        assert not any(a.startswith(("--keep-open", "--force-window")) for a in argv)


class TestLifecycle:
    def test_start_observes_idle_and_close_quits(self, fake_mpv):
        ipc, mpv = _started()
        sock_dir = ipc._dir
        assert mpv.commands[0] == ["observe_property", 1, "idle-active"]
        ipc.close()
        assert mpv.commands[-1] == ["quit"]
        assert mpv.exited.is_set()
        assert not os.path.exists(sock_dir)
        ipc.close()  # idempotent

    def test_dead_process_fails_fast(self, monkeypatch):
        class _Dead:
            def __init__(self, *a, **k):
                pass

            def poll(self):
                return 1

        monkeypatch.setattr(mpv_ipc.subprocess, "Popen", _Dead)
        t0 = time.monotonic()
        with pytest.raises(MpvIpcError, match="exited before"):
            MpvIpc("mpv").start(connect_timeout=5)
        assert time.monotonic() - t0 < 1

    def test_missing_binary(self, monkeypatch):
        monkeypatch.setattr(mpv_ipc.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(OSError("nope")))
        with pytest.raises(MpvIpcError, match="could not start"):
            MpvIpc("mpv").start()

    def test_close_kills_mpv_that_ignores_quit(self, fake_mpv):
        ipc, mpv = _started()
        mpv.answer = False
        with patch.object(mpv, "wait", side_effect=[subprocess.TimeoutExpired("mpv", 2), 0]):
            ipc.close()
        assert getattr(mpv, "killed", False)


class TestCommands:
    def test_append_uses_absolute_path_and_append_play(self, fake_mpv, tmp_path):
        ipc, mpv = _started()
        ipc.append("rel.mp3")
        assert mpv.commands[-1] == ["loadfile", os.path.abspath("rel.mp3"), "append-play"]
        ipc.close()

    def test_controls_wire_format(self, fake_mpv):
        ipc, mpv = _started()
        ipc.pause()
        ipc.resume()
        ipc.skip()
        ipc.stop()
        assert mpv.commands[1:] == [
            ["set_property", "pause", True],
            ["set_property", "pause", False],
            ["playlist-next", "force"],
            ["stop"],
        ]
        ipc.close()

    def test_unanswered_command_times_out(self, fake_mpv):
        ipc, mpv = _started()
        mpv.answer = False
        with pytest.raises(MpvIpcError, match="did not answer"):
            ipc.command("get_property", "pause", timeout=0.2)
        mpv._exit()
        ipc.close(quit=False)

    def test_error_reply_raises(self, fake_mpv):
        ipc, mpv = _started()
        mpv.answer = False

        def reply_error():
            time.sleep(0.05)
            mpv.emit({"request_id": ipc._next_id - 1, "error": "invalid parameter"})

        threading.Thread(target=reply_error, daemon=True).start()
        with pytest.raises(MpvIpcError, match="invalid parameter"):
            ipc.command("loadfile", "/x.mp3", "bogus-mode", timeout=1)
        mpv._exit()
        ipc.close(quit=False)


class TestWaitDone:
    def test_waits_for_every_entry_and_idle(self, fake_mpv):
        ipc, mpv = _started()
        ipc.append("a.mp3")
        ipc.append("b.mp3")
        assert ipc.wait_done(timeout=0.2) is False   # nothing finished yet
        mpv.finish(1, idle=True)                      # idle between chunks (synthesis gap)
        assert ipc.wait_done(timeout=0.2) is False   # b still pending
        mpv.finish(2)
        assert ipc.wait_done(timeout=2) is True
        ipc.close()

    def test_appending_after_idle_gap_keeps_waiting(self, fake_mpv):
        ipc, mpv = _started()
        ipc.append("a.mp3")
        mpv.finish(1)
        assert ipc.wait_done(timeout=2) is True
        ipc.append("late.mp3")                        # the chunk that used to be lost
        assert ipc.wait_done(timeout=0.2) is False
        mpv.finish(2)
        assert ipc.wait_done(timeout=2) is True
        ipc.close()

    def test_stop_and_disconnect_end_the_wait(self, fake_mpv):
        ipc, mpv = _started()
        ipc.append("a.mp3")
        ipc.stop()
        assert ipc.wait_done(timeout=1) is True
        ipc.close()

        ipc2, mpv2 = _started()
        ipc2.append("a.mp3")
        mpv2._exit()                                   # mpv died mid-playback
        assert ipc2.wait_done(timeout=2) is True
        ipc2.close(quit=False)

    def test_should_continue_aborts(self, fake_mpv):
        ipc, _ = _started()
        ipc.append("a.mp3")
        assert ipc.wait_done(should_continue=lambda: False) is False
        ipc.close()

    def test_error_entry_reports_and_counts_as_ended(self, fake_mpv):
        errors = []
        ipc, mpv = _started(on_error=errors.append)
        ipc.append("bad.mp3")
        mpv.finish(1, reason="error")
        assert ipc.wait_done(timeout=2) is True
        assert errors and errors[0]["playlist_entry_id"] == 1
        ipc.close()


@pytest.mark.integration
@pytest.mark.skipif(not (shutil.which("mpv") and shutil.which("ffmpeg")),
                    reason="needs mpv and ffmpeg")
def test_real_mpv_plays_across_a_gap(tmp_path):
    """Real mpv (null audio out): a chunk appended after mpv went idle still plays."""
    clip = tmp_path / "silence.mp3"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                    "-t", "0.4", "-q:a", "9", str(clip)], check=True)
    ipc = MpvIpc("mpv")
    ipc.argv = lambda sock, _argv=ipc.argv: _argv(sock) + ["--ao=null"]
    ipc.start()
    try:
        ipc.append(str(clip))
        assert ipc.wait_done(timeout=10)
        ipc.append(str(clip))  # mpv is idle now; append-play must restart playback
        assert ipc.wait_done(timeout=10)
        assert len(ipc._ended) == 2
    finally:
        ipc.close()
