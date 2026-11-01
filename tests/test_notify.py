"""Tests for the start-of-read desktop notification."""

import os
import subprocess
import time

import pytest

from TTS_ka import notify
from TTS_ka.user_config import apply_env_from_config


@pytest.mark.parametrize("rate,expected", [
    (None, 1.0), ("+0%", 1.0), ("+30%", 1.3), ("-50%", 0.5), ("garbage", 1.0), ("+5Hz", 1.0),
])
def test_rate_factor(rate, expected):
    assert notify.rate_factor(rate) == pytest.approx(expected)


def test_estimate_uses_per_language_speed():
    text = " ".join(["word"] * 115)
    assert notify.estimate_speech_seconds(text, "ka") == pytest.approx(60.0)
    assert notify.estimate_speech_seconds(text, "en") < notify.estimate_speech_seconds(text, "ru")
    assert notify.estimate_speech_seconds(text, "xx") == pytest.approx(115 / 150 * 60)


def test_estimate_faster_rate_is_shorter():
    text = " ".join(["word"] * 180)
    assert notify.estimate_speech_seconds(text, "en", "+100%") == pytest.approx(30.0)


@pytest.mark.parametrize("seconds,expected", [
    (0, "1 s"), (42.4, "42 s"), (59.6, "1 min"), (430, "7 min"),
    (3600, "1 h"), (4500, "1 h 15 min"), (3900, "1 h 05 min"),
])
def test_format_duration(seconds, expected):
    assert notify.format_duration(seconds) == expected


def test_message_includes_end_time_for_long_reads():
    text = " ".join(["word"] * 1150)  # 10 min of Georgian
    now = time.mktime((2026, 1, 1, 12, 0, 0, 0, 0, -1))
    summary, body = notify.reading_started_message(text, "ka", now=now)
    assert summary == "🔊 Reading ~10 min"
    assert body == "1,150 words · ka · done ≈ 12:10"


def test_message_short_read_has_no_end_time():
    summary, body = notify.reading_started_message("Hello there", "en")
    assert summary.startswith("🔊 Reading ~")
    assert "done" not in body


def _linux_with_notify_send(monkeypatch):
    monkeypatch.setattr(notify.sys, "platform", "linux")
    monkeypatch.setattr(notify.shutil, "which", lambda name: "/usr/bin/notify-send")
    monkeypatch.delenv("TTS_KA_NOTIFY", raising=False)


def test_enabled_only_on_linux_with_notify_send(monkeypatch):
    _linux_with_notify_send(monkeypatch)
    assert notify.notifications_enabled()
    monkeypatch.setattr(notify.sys, "platform", "win32")
    assert not notify.notifications_enabled()
    monkeypatch.setattr(notify.sys, "platform", "linux")
    monkeypatch.setattr(notify.shutil, "which", lambda name: None)
    assert not notify.notifications_enabled()


@pytest.mark.parametrize("value", ["0", "false", "off"])
def test_env_disables(monkeypatch, value):
    _linux_with_notify_send(monkeypatch)
    monkeypatch.setenv("TTS_KA_NOTIFY", value)
    assert not notify.notifications_enabled()


def test_config_notify_false_sets_env(monkeypatch):
    monkeypatch.delenv("TTS_KA_NOTIFY", raising=False)
    apply_env_from_config({"notify": False})
    assert os.environ["TTS_KA_NOTIFY"] == "0"


def test_notify_reading_started_calls_notify_send(monkeypatch):
    _linux_with_notify_send(monkeypatch)
    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(notify.subprocess, "run", fake_run)
    assert notify.notify_reading_started("one two three", "en")
    argv = calls[0]
    assert argv[0] == "/usr/bin/notify-send"
    assert "-a" in argv and "TTS_ka" in argv
    assert any(a.startswith("🔊 Reading ~") for a in argv)
    assert argv[-1].startswith("3 words · en")


def test_notify_disabled_does_not_run(monkeypatch):
    _linux_with_notify_send(monkeypatch)
    monkeypatch.setenv("TTS_KA_NOTIFY", "0")
    monkeypatch.setattr(notify.subprocess, "run",
                        lambda *a, **k: pytest.fail("notify-send must not run"))
    assert not notify.notify_reading_started("hello", "en")


@pytest.mark.parametrize("exc", [OSError("boom"), subprocess.TimeoutExpired("x", 3)])
def test_send_notification_never_raises(monkeypatch, exc):
    _linux_with_notify_send(monkeypatch)

    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(notify.subprocess, "run", boom)
    assert notify.send_notification("hi") is False


def test_send_notification_without_binary(monkeypatch):
    monkeypatch.setattr(notify.shutil, "which", lambda name: None)
    assert notify.send_notification("hi") is False


def test_send_notification_nonzero_exit(monkeypatch):
    _linux_with_notify_send(monkeypatch)
    monkeypatch.setattr(notify.subprocess, "run",
                        lambda argv, **k: subprocess.CompletedProcess(argv, 1))
    assert notify.send_notification("hi", "body") is False
