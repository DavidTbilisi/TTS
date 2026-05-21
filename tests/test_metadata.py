"""FEAT-5: ID3 tags + chapter markers via mutagen (optional dep)."""

from __future__ import annotations

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from TTS_ka import metadata as md


class TestLoadChapters:
    def test_loads_valid_json(self, tmp_path):
        f = tmp_path / "ch.json"
        f.write_text(json.dumps([
            {"title": "Ch 1", "start_ms": 0, "end_ms": 5000},
            {"title": "Ch 2", "start_ms": 5000, "end_ms": 10000},
        ]), encoding="utf-8")
        chapters = md.load_chapters(str(f))
        assert len(chapters) == 2
        assert chapters[0].title == "Ch 1"
        assert chapters[0].end_ms == 5000

    def test_rejects_non_array(self, tmp_path):
        f = tmp_path / "ch.json"
        f.write_text('{"not": "an array"}', encoding="utf-8")
        with pytest.raises(ValueError):
            md.load_chapters(str(f))

    def test_rejects_malformed_entry(self, tmp_path):
        f = tmp_path / "ch.json"
        f.write_text(json.dumps([{"title": "Ch 1"}]),  # missing keys
                     encoding="utf-8")
        with pytest.raises(ValueError):
            md.load_chapters(str(f))


class TestMetadataSpec:
    def test_empty_is_empty(self):
        assert md.MetadataSpec().is_empty()

    def test_any_field_makes_it_non_empty(self):
        assert not md.MetadataSpec(title="x").is_empty()
        assert not md.MetadataSpec(author="x").is_empty()
        assert not md.MetadataSpec(cover_path="x").is_empty()
        assert not md.MetadataSpec(chapters=[md.Chapter("a", 0, 1)]).is_empty()


class TestApply:
    def test_empty_spec_noop(self, tmp_path):
        """An empty spec must NOT attempt to import mutagen."""
        f = tmp_path / "a.mp3"
        f.write_bytes(b"fake")
        # If mutagen weren't optional, this would fail on import. Confirm no-op.
        with patch.dict(sys.modules, {"mutagen": None, "mutagen.id3": None}):
            md.apply(str(f), md.MetadataSpec())  # must not raise

    def test_apply_missing_mutagen_raises_actionable(self, tmp_path):
        f = tmp_path / "a.mp3"
        f.write_bytes(b"fake")
        spec = md.MetadataSpec(title="hi")
        with patch.dict(sys.modules, {"mutagen.id3": None}):
            with pytest.raises(md.MissingExtraError) as exc:
                md.apply(str(f), spec)
        assert "TTS_ka[metadata]" in str(exc.value)

    def test_apply_writes_title_and_author_via_mutagen(self, tmp_path):
        f = tmp_path / "a.mp3"
        f.write_bytes(b"fake")

        # Build a fake mutagen.id3 module
        recorded_frames = []
        saved = []

        class FakeFrame:
            def __init__(self, **kw):
                self.kw = kw

            @property
            def FrameID(self):
                return type(self).__name__

        class TIT2(FakeFrame): pass
        class TPE1(FakeFrame): pass
        class TALB(FakeFrame): pass
        class APIC(FakeFrame): pass
        class CHAP(FakeFrame): pass
        class CTOC(FakeFrame): pass

        class ID3NoHeaderError(Exception): pass

        class FakeID3:
            def __init__(self, path=None):
                if path is None:
                    return
                # Pretend the file has no ID3 header so the constructor raises
                raise ID3NoHeaderError()

            def add(self, frame):
                recorded_frames.append(frame)

            def delall(self, name):
                pass

            def save(self, path):
                saved.append(path)

        fake_mod = MagicMock(
            ID3=FakeID3, TIT2=TIT2, TPE1=TPE1, TALB=TALB, APIC=APIC,
            CHAP=CHAP, CTOC=CTOC, ID3NoHeaderError=ID3NoHeaderError,
        )
        spec = md.MetadataSpec(title="My Title", author="My Author")
        with patch.dict(sys.modules, {"mutagen.id3": fake_mod}):
            md.apply(str(f), spec)

        # Confirm both frames were added and the file was saved
        frame_types = {type(fr).__name__ for fr in recorded_frames}
        assert "TIT2" in frame_types
        assert "TPE1" in frame_types
        assert saved == [str(f)]

    def test_apply_chapters_writes_chap_and_ctoc(self, tmp_path):
        f = tmp_path / "a.mp3"
        f.write_bytes(b"fake")
        recorded = []

        class TIT2:
            def __init__(self, **kw): self.kw = kw

        class CHAP:
            def __init__(self, **kw):
                self.kw = kw
                recorded.append(("CHAP", kw))

        class CTOC:
            def __init__(self, **kw):
                self.kw = kw
                recorded.append(("CTOC", kw))

        class ID3:
            def __init__(self, path=None): pass
            def add(self, frame): pass
            def delall(self, name): pass
            def save(self, path): pass

        fake_mod = MagicMock(
            ID3=ID3, TIT2=TIT2, TPE1=MagicMock(), TALB=MagicMock(),
            APIC=MagicMock(), CHAP=CHAP, CTOC=CTOC,
            ID3NoHeaderError=Exception,
        )
        chapters = [
            md.Chapter("Ch 1", 0, 5000),
            md.Chapter("Ch 2", 5000, 10000),
            md.Chapter("Ch 3", 10000, 15000),
        ]
        spec = md.MetadataSpec(chapters=chapters)
        with patch.dict(sys.modules, {"mutagen.id3": fake_mod}):
            md.apply(str(f), spec)

        chap_records = [r for r in recorded if r[0] == "CHAP"]
        ctoc_records = [r for r in recorded if r[0] == "CTOC"]
        assert len(chap_records) == 3
        assert len(ctoc_records) == 1
        # Each CHAP element_id present in CTOC child list
        child_ids = ctoc_records[0][1]["child_element_ids"]
        for i in range(3):
            assert f"ch{i}" in child_ids


class TestCLIIntegration:
    def test_no_metadata_flags_skips_apply(self, tmp_path):
        with patch("sys.argv", ["TTS_ka", "hi", "--lang", "en", "--no-play"]), \
             patch("TTS_ka.main.fast_generate_audio",
                   new=AsyncMock(return_value=True)), \
             patch("TTS_ka.main.cleanup_http", new=AsyncMock()), \
             patch("TTS_ka.main.get_optimal_settings",
                   return_value={"method": "direct", "chunk_seconds": 0, "parallel": 1}), \
             patch("TTS_ka.main._metadata.apply") as mapply:
            from TTS_ka.main import main
            main()
        # No metadata flags => apply never called
        mapply.assert_not_called()

    def test_title_flag_triggers_metadata_apply(self, tmp_path):
        with patch("sys.argv", ["TTS_ka", "hi", "--lang", "en", "--no-play",
                                "--title", "My Book"]), \
             patch("TTS_ka.main.fast_generate_audio",
                   new=AsyncMock(return_value=True)), \
             patch("TTS_ka.main.cleanup_http", new=AsyncMock()), \
             patch("TTS_ka.main.get_optimal_settings",
                   return_value={"method": "direct", "chunk_seconds": 0, "parallel": 1}), \
             patch("TTS_ka.main._metadata.apply") as mapply:
            from TTS_ka.main import main
            main()
        mapply.assert_called_once()
        spec = mapply.call_args.args[1]
        assert spec.title == "My Book"

    def test_chapters_flag_loads_and_applies(self, tmp_path):
        ch_file = tmp_path / "ch.json"
        ch_file.write_text(json.dumps([
            {"title": "Intro", "start_ms": 0, "end_ms": 3000}
        ]), encoding="utf-8")
        with patch("sys.argv", ["TTS_ka", "hi", "--lang", "en", "--no-play",
                                "--chapters", str(ch_file)]), \
             patch("TTS_ka.main.fast_generate_audio",
                   new=AsyncMock(return_value=True)), \
             patch("TTS_ka.main.cleanup_http", new=AsyncMock()), \
             patch("TTS_ka.main.get_optimal_settings",
                   return_value={"method": "direct", "chunk_seconds": 0, "parallel": 1}), \
             patch("TTS_ka.main._metadata.apply") as mapply:
            from TTS_ka.main import main
            main()
        spec = mapply.call_args.args[1]
        assert spec.chapters is not None
        assert len(spec.chapters) == 1
        assert spec.chapters[0].title == "Intro"
