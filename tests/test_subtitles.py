"""FEAT-6: SRT / VTT export driven by edge-tts WordBoundary events."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from TTS_ka import subtitles
from TTS_ka.subtitles import WordEvent


def _events(*pairs):
    """Build WordEvents from (text, start_ms, duration_ms) tuples."""
    return [WordEvent(text=t, start_ms=s, duration_ms=d) for t, s, d in pairs]


class TestGroupingAndFormatting:
    def test_format_ts_srt(self):
        assert subtitles._format_ts(0) == "00:00:00,000"
        assert subtitles._format_ts(1_500) == "00:00:01,500"
        assert subtitles._format_ts(3_661_500) == "01:01:01,500"

    def test_format_ts_vtt(self):
        assert subtitles._format_ts(3_661_500, sep=".") == "01:01:01.500"

    def test_srt_basic_structure(self):
        evts = _events(
            ("Hello", 0, 400),
            ("world", 400, 600),
        )
        out = subtitles.events_to_srt(evts)
        assert "1\n" in out
        assert "00:00:00,000 --> 00:00:01,000" in out
        assert "Hello world" in out

    def test_vtt_starts_with_header(self):
        evts = _events(("Hi", 0, 500))
        out = subtitles.events_to_vtt(evts)
        assert out.startswith("WEBVTT")
        assert "00:00:00.000 --> 00:00:00.500" in out

    def test_grouping_splits_after_max_words(self):
        many = [(f"w{i}", i * 200, 200) for i in range(20)]
        evts = _events(*many)
        groups = subtitles._group(evts)
        # 20 words / 8 per line = 3 groups
        assert len(groups) >= 3

    def test_grouping_splits_after_max_line_duration(self):
        # 3 words each spanning 2 seconds = 6 seconds total > MAX_LINE_MS (4s)
        evts = _events(
            ("first", 0, 2000),
            ("second", 2000, 2000),
            ("third", 4000, 2000),
        )
        groups = subtitles._group(evts)
        assert len(groups) >= 2

    def test_srt_timings_monotonic(self):
        evts = _events(
            ("a", 0, 500),
            ("b", 500, 500),
            ("c", 1000, 500),
            ("d", 1500, 500),
            ("e", 2000, 500),
            ("f", 2500, 500),
            ("g", 3000, 500),
            ("h", 3500, 500),
            ("i", 4000, 500),
        )
        out = subtitles.events_to_srt(evts)
        import re
        timestamps = re.findall(r"(\d{2}:\d{2}:\d{2}),\d{3}", out)
        starts = [t for i, t in enumerate(timestamps) if i % 2 == 0]
        assert starts == sorted(starts)

    def test_text_concatenation_matches_input(self):
        evts = _events(
            ("Hello", 0, 400),
            ("brave", 400, 400),
            ("new", 800, 400),
            ("world", 1200, 400),
        )
        out = subtitles.events_to_srt(evts)
        for word in ("Hello", "brave", "new", "world"):
            assert word in out

    def test_negative_ms_clamped_to_zero(self):
        assert subtitles._format_ts(-50) == "00:00:00,000"

    def test_empty_events_produce_minimal_output(self):
        assert subtitles.events_to_srt([]) == ""
        assert subtitles.events_to_vtt([]).startswith("WEBVTT")


class TestWriteSubs:
    def test_write_srt_file(self, tmp_path):
        evts = _events(("hi", 0, 500))
        out = tmp_path / "out.srt"
        subtitles.write_subs(evts, str(out), "srt")
        assert out.read_text(encoding="utf-8").startswith("1\n00:00:00,000")

    def test_write_vtt_file(self, tmp_path):
        evts = _events(("hi", 0, 500))
        out = tmp_path / "out.vtt"
        subtitles.write_subs(evts, str(out), "vtt")
        assert out.read_text(encoding="utf-8").startswith("WEBVTT")

    def test_unknown_format_raises(self, tmp_path):
        with pytest.raises(ValueError):
            subtitles.write_subs([], str(tmp_path / "x.bin"), "bin")


class TestGenerateAudioWithSubs:
    """fast_audio.generate_audio_with_subs uses edge-tts streaming."""

    async def test_collects_word_boundary_events(self, tmp_path):
        from TTS_ka import fast_audio

        chunks_yielded = [
            {"type": "audio", "data": b"\x00\x01"},
            {"type": "WordBoundary", "offset": 0,         "duration": 5_000_000, "text": "hello"},
            {"type": "audio", "data": b"\x02\x03"},
            {"type": "WordBoundary", "offset": 5_000_000, "duration": 5_000_000, "text": "world"},
            {"type": "audio", "data": b"\x04"},
        ]

        class FakeCommunicate:
            def __init__(self, *args, **kwargs):
                pass

            async def stream(self):
                for c in chunks_yielded:
                    yield c

        fake_mod = MagicMock(Communicate=FakeCommunicate)
        with patch.dict("sys.modules", {"edge_tts": fake_mod}):
            events = await fast_audio.generate_audio_with_subs(
                "hello world", "en", str(tmp_path / "out.mp3"),
            )
        # offsets are 100-ns ticks; converted to ms
        assert [(e.text, e.start_ms, e.duration_ms) for e in events] == [
            ("hello", 0, 500),
            ("world", 500, 500),
        ]
        # Audio data was written
        audio_bytes = (tmp_path / "out.mp3").read_bytes()
        assert audio_bytes == b"\x00\x01\x02\x03\x04"


class TestCLI:
    def test_srt_flag_writes_srt_alongside_mp3(self, tmp_path):
        out = tmp_path / "narration.mp3"
        with patch("sys.argv", ["TTS_ka", "hello world", "--lang", "en",
                                "--output", str(out), "--no-play", "--srt"]):
            with patch("TTS_ka.main.generate_audio_with_subs",
                       new=AsyncMock(return_value=[
                           WordEvent("hello", 0, 500),
                           WordEvent("world", 500, 500),
                       ])) as mgen, \
                 patch("TTS_ka.main.cleanup_http", new=AsyncMock()), \
                 patch("TTS_ka.main.get_optimal_settings",
                       return_value={"method": "direct", "chunk_seconds": 0, "parallel": 1}):
                from TTS_ka.main import main
                main()
        mgen.assert_called_once()
        srt = tmp_path / "narration.srt"
        assert srt.exists()
        content = srt.read_text(encoding="utf-8")
        assert "hello world" in content

    def test_vtt_flag_writes_vtt_alongside_mp3(self, tmp_path):
        out = tmp_path / "narration.mp3"
        with patch("sys.argv", ["TTS_ka", "hi", "--lang", "en",
                                "--output", str(out), "--no-play", "--vtt"]):
            with patch("TTS_ka.main.generate_audio_with_subs",
                       new=AsyncMock(return_value=[WordEvent("hi", 0, 500)])), \
                 patch("TTS_ka.main.cleanup_http", new=AsyncMock()), \
                 patch("TTS_ka.main.get_optimal_settings",
                       return_value={"method": "direct", "chunk_seconds": 0, "parallel": 1}):
                from TTS_ka.main import main
                main()
        vtt = tmp_path / "narration.vtt"
        assert vtt.exists()
        assert vtt.read_text(encoding="utf-8").startswith("WEBVTT")

    def test_both_srt_and_vtt_write_both_files(self, tmp_path):
        out = tmp_path / "x.mp3"
        with patch("sys.argv", ["TTS_ka", "hi", "--lang", "en",
                                "--output", str(out), "--no-play", "--srt", "--vtt"]):
            with patch("TTS_ka.main.generate_audio_with_subs",
                       new=AsyncMock(return_value=[WordEvent("hi", 0, 500)])), \
                 patch("TTS_ka.main.cleanup_http", new=AsyncMock()), \
                 patch("TTS_ka.main.get_optimal_settings",
                       return_value={"method": "direct", "chunk_seconds": 0, "parallel": 1}):
                from TTS_ka.main import main
                main()
        assert (tmp_path / "x.srt").exists()
        assert (tmp_path / "x.vtt").exists()
