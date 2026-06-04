"""Tests for session_log — JSONL append-only training log."""

import json
import os

import pytest

from TTS_ka import session_log
from TTS_ka.session_log import SessionRecord, append, default_log_path, read_all


class TestSessionRecord:
    def test_wpm_computation(self):
        rec = SessionRecord(
            date="2026-06-04T11:00:00+00:00",
            text_hash="abc",
            voice="en",
            word_count=600,
            duration_ms=300_000,
            chunks_done=3,
        )
        assert rec.wpm == pytest.approx(120.0, rel=1e-6)

    def test_wpm_zero_duration(self):
        rec = SessionRecord(
            date="2026-06-04T11:00:00+00:00",
            text_hash="abc",
            voice="en",
            word_count=100,
            duration_ms=0,
            chunks_done=0,
        )
        assert rec.wpm == 0.0

    def test_now_constructor_uses_iso(self):
        rec = SessionRecord.now(
            text_hash="x",
            voice="en",
            word_count=10,
            duration_ms=10_000,
            chunks_done=1,
        )
        assert rec.date.endswith("+00:00") or "Z" in rec.date


class TestPathResolution:
    def test_default_path_under_home(self):
        # Clear the override so we test the real default.
        os.environ.pop("TTS_KA_STUDY_LOG", None)
        assert str(default_log_path()).endswith(".tts_ka_study.jsonl")

    def test_env_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TTS_KA_STUDY_LOG", str(tmp_path / "study.jsonl"))
        assert default_log_path() == tmp_path / "study.jsonl"


class TestAppendAndRead:
    def test_round_trip(self, tmp_path):
        log = tmp_path / "log.jsonl"
        rec = SessionRecord(
            date="2026-06-04T11:00:00+00:00",
            text_hash="hash1",
            voice="en",
            word_count=200,
            duration_ms=60_000,
            chunks_done=1,
        )
        append(rec, path=log)
        out = read_all(path=log)
        assert len(out) == 1
        assert out[0] == rec

    def test_multiple_appends_preserved_in_order(self, tmp_path):
        log = tmp_path / "log.jsonl"
        recs = [
            SessionRecord(
                date=f"2026-06-0{i}T11:00:00+00:00",
                text_hash=f"h{i}",
                voice="en",
                word_count=100 * i,
                duration_ms=10_000,
                chunks_done=i,
            )
            for i in range(1, 4)
        ]
        for r in recs:
            append(r, path=log)
        assert read_all(path=log) == recs

    def test_read_missing_file(self, tmp_path):
        assert read_all(path=tmp_path / "does_not_exist.jsonl") == []

    def test_skips_malformed_lines(self, tmp_path):
        log = tmp_path / "log.jsonl"
        log.write_text(
            "not json at all\n"
            + json.dumps({
                "date": "2026-06-04T11:00:00+00:00",
                "text_hash": "ok",
                "voice": "en",
                "word_count": 10,
                "duration_ms": 1000,
                "chunks_done": 1,
            })
            + "\n"
            + "{}\n",  # valid JSON but missing required fields → skipped
            encoding="utf-8",
        )
        out = read_all(path=log)
        assert len(out) == 1
        assert out[0].text_hash == "ok"

    def test_creates_parent_dir(self, tmp_path):
        nested = tmp_path / "nest" / "sub" / "log.jsonl"
        rec = SessionRecord(
            date="2026-06-04T11:00:00+00:00",
            text_hash="h",
            voice="en",
            word_count=1,
            duration_ms=1,
            chunks_done=0,
        )
        append(rec, path=nested)
        assert nested.exists()
