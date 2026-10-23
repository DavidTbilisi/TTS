"""Tests for ultra_fast module."""

import asyncio
import os
import time

import pytest
import threading
from unittest.mock import MagicMock, patch, AsyncMock
from TTS_ka.fast_audio import GenerationFailed
from TTS_ka.ultra_fast import (
    ultra_fast_parallel_generation,
    ultra_fast_cleanup_parts,
    smart_generate_long_text,
    get_optimal_settings,
    OPTIMAL_WORKERS,
    GenerationCancelled,
)


class TestGetOptimalSettings:
    def test_short_text_direct(self):
        text = "Hello world"  # < 100 words
        result = get_optimal_settings(text)
        assert result['method'] == 'direct'
        assert result['chunk_seconds'] == 0
        assert result['parallel'] == 1

    def test_medium_text_smart(self):
        text = "word " * 200  # 200 words
        result = get_optimal_settings(text)
        assert result['method'] == 'smart'
        assert result['chunk_seconds'] > 0
        assert result['parallel'] >= 1

    def test_long_text_smart_more_workers(self):
        text = "word " * 600  # 600 words
        result = get_optimal_settings(text)
        assert result['method'] == 'smart'
        assert result['parallel'] >= 2

    def test_very_long_text(self):
        text = "word " * 3000  # 3000 words
        result = get_optimal_settings(text)
        assert result['method'] == 'smart'
        assert result['parallel'] == OPTIMAL_WORKERS

    def test_returns_dict_with_required_keys(self):
        result = get_optimal_settings("hello")
        assert 'method' in result
        assert 'chunk_seconds' in result
        assert 'parallel' in result

    @pytest.mark.parametrize("word_count", [50, 150, 600, 2500])
    def test_various_lengths_return_valid_settings(self, word_count):
        text = "word " * word_count
        result = get_optimal_settings(text)
        assert result['method'] in ('direct', 'smart')
        assert result['chunk_seconds'] >= 0
        assert result['parallel'] >= 1


class TestOptimalWorkers:
    def test_optimal_workers_positive(self):
        assert OPTIMAL_WORKERS >= 1

    def test_optimal_workers_bounded(self):
        assert OPTIMAL_WORKERS <= 32


class TestUltraFastCleanupParts:
    def test_deletes_existing_files(self, tmp_path):
        f = tmp_path / "part.mp3"
        f.write_bytes(b"data")
        ultra_fast_cleanup_parts([str(f)])
        assert not f.exists()

    def test_skips_nonexistent_files(self):
        ultra_fast_cleanup_parts(["/nonexistent/fake.mp3"])  # must not raise

    def test_keep_parts_skips_deletion(self, tmp_path):
        f = tmp_path / "part.mp3"
        f.write_bytes(b"data")
        ultra_fast_cleanup_parts([str(f)], keep_parts=True)
        assert f.exists()  # file was kept

    def test_empty_list(self):
        ultra_fast_cleanup_parts([])  # must not raise

    def test_deletes_many_files(self, tmp_path):
        files = []
        for i in range(10):
            f = tmp_path / f"part_{i}.mp3"
            f.write_bytes(b"x")
            files.append(str(f))
        ultra_fast_cleanup_parts(files)
        for f in files:
            assert not os.path.exists(f)


class TestUltraFastParallelGeneration:
    async def test_cancel_before_start_raises(self, tmp_path):
        chunks = ["a", "b"]
        output_path = str(tmp_path / "out.mp3")
        ev = threading.Event()
        ev.set()
        with patch("TTS_ka.ultra_fast.fast_generate_audio", new=AsyncMock(return_value=True)):
            with pytest.raises(GenerationCancelled):
                await ultra_fast_parallel_generation(
                    chunks, "en", parallel=2, output_path=output_path, cancel_event=ev
                )

    async def test_progress_callback_invoked(self, tmp_path):
        chunks = ["Hello", "world"]
        output_path = str(tmp_path / "out.mp3")
        seen: list[tuple[int, int]] = []

        def cb(done: int, total: int) -> None:
            seen.append((done, total))

        with patch("TTS_ka.ultra_fast.fast_generate_audio", new=AsyncMock(return_value=True)):
            await ultra_fast_parallel_generation(
                chunks, "en", parallel=2, output_path=output_path, progress_callback=cb
            )
        assert (0, 2) in seen
        assert seen[-1] == (2, 2)

    async def test_success_returns_parts(self, tmp_path):
        chunks = ["Hello world", "Second chunk"]
        output_path = str(tmp_path / "out.mp3")

        with patch('TTS_ka.ultra_fast.fast_generate_audio', new=AsyncMock(return_value=True)), \
             patch('TTS_ka.ultra_fast.create_progress_display') as mock_cpd:
            mock_display = MagicMock()
            mock_cpd.return_value = mock_display
            parts = await ultra_fast_parallel_generation(chunks, "en", parallel=2, output_path=output_path)

        assert len(parts) == 2

    async def test_partial_failure_raises_and_cleans_up(self, tmp_path):
        """A missing chunk means missing text: raise instead of merging a gap."""
        chunks = ["chunk one", "chunk two", "chunk three"]
        output_path = str(tmp_path / "out.mp3")
        results = iter([True, False, True])

        async def fake(text, lang, out, **kw):
            with open(out, "wb") as f:
                f.write(b"audio")
            return next(results)

        cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch('TTS_ka.ultra_fast.fast_generate_audio', side_effect=fake), \
                 patch('TTS_ka.ultra_fast.create_progress_display', return_value=MagicMock()):
                with pytest.raises(GenerationFailed, match="1 of 3 chunks failed"):
                    await ultra_fast_parallel_generation(chunks, "en", parallel=1,
                                                         output_path=output_path)
            assert not any(n.startswith(".part_") for n in os.listdir(tmp_path))
        finally:
            os.chdir(cwd)

    async def test_parts_live_in_work_dir_never_output_path(self, tmp_path):
        chunks = ["chunk one", "chunk two"]
        output_path = str(tmp_path / "out.mp3")
        work_dir = tmp_path / "run"
        work_dir.mkdir()
        mock_player = MagicMock()
        mock_player.add_chunk = MagicMock()

        with patch('TTS_ka.ultra_fast.fast_generate_audio', new=AsyncMock(return_value=True)), \
             patch('TTS_ka.ultra_fast.create_progress_display', return_value=MagicMock()):
            parts = await ultra_fast_parallel_generation(
                chunks, "en", parallel=2, streaming_player=mock_player,
                output_path=output_path, work_dir=str(work_dir),
            )

        assert parts == [str(work_dir / ".part_0000.mp3"), str(work_dir / ".part_0001.mp3")]
        assert output_path not in parts
        mock_player.add_chunk.assert_any_call(parts[0], 0)

    async def test_exception_in_worker_reported(self, tmp_path, capsys):
        chunks = ["bad chunk"]
        output_path = str(tmp_path / "out.mp3")

        with patch('TTS_ka.ultra_fast.fast_generate_audio', new=AsyncMock(side_effect=Exception("oops"))), \
             patch('TTS_ka.ultra_fast.create_progress_display', return_value=MagicMock()):
            with pytest.raises(GenerationFailed, match="1 of 1 chunks failed to synthesize: oops"):
                await ultra_fast_parallel_generation(chunks, "en", parallel=1, output_path=output_path)

        # The per-chunk warning is still printed (stderr via rich console)
        captured = capsys.readouterr()
        assert "oops" in (captured.out + captured.err)


class TestSmartGenerateLongText:
    async def test_direct_failure_raises_and_removes_empty_output(self, tmp_path, capsys):
        output_path = str(tmp_path / "out.mp3")

        async def fake(text, lang, out, **kw):
            open(out, "wb").close()  # edge-tts leaves a 0-byte file on 403
            return False

        with patch('TTS_ka.ultra_fast.fast_generate_audio', side_effect=fake):
            with pytest.raises(GenerationFailed, match="Audio generation failed"):
                await smart_generate_long_text("short text", "en", output_path=output_path)
        assert not os.path.exists(output_path)
        assert "Completed" not in capsys.readouterr().err

    async def test_short_text_direct_generation(self, tmp_path, capsys):
        """Very short text (< 200 words, no streaming) goes direct."""
        output_path = str(tmp_path / "out.mp3")
        text = "Hello world"

        with patch('TTS_ka.ultra_fast.fast_generate_audio', new=AsyncMock(return_value=True)) as mfa:
            await smart_generate_long_text(text, "en", output_path=output_path)

        mfa.assert_called_once()
        captured = capsys.readouterr()
        assert "direct" in (captured.out + captured.err)

    async def test_long_text_uses_chunks(self, tmp_path):
        """Long text is split into chunks and merged."""
        output_path = str(tmp_path / "out.mp3")
        text = "word " * 300

        with patch('TTS_ka.ultra_fast.ultra_fast_parallel_generation', new=AsyncMock(return_value=[output_path])) as mupg, \
             patch('TTS_ka.ultra_fast.fast_merge_audio_files'), \
             patch('TTS_ka.ultra_fast.create_progress_display', return_value=MagicMock()):
            await smart_generate_long_text(text, "en", chunk_seconds=20, parallel=2, output_path=output_path)

        mupg.assert_called_once()

    async def test_empty_chunks_raises(self, tmp_path):
        output_path = str(tmp_path / "out.mp3")

        with patch('TTS_ka.chunking.split_text_into_chunks', return_value=[]):
            with pytest.raises(ValueError, match="No text chunks"):
                await smart_generate_long_text("word " * 300, "en", chunk_seconds=20, output_path=output_path)

    @pytest.mark.parametrize("lang", ["ka", "ka-m", "ru", "en"])
    async def test_supported_languages(self, tmp_path, lang):
        output_path = str(tmp_path / f"out_{lang}.mp3")
        with patch('TTS_ka.ultra_fast.fast_generate_audio', new=AsyncMock(return_value=True)):
            await smart_generate_long_text("hello", lang, output_path=output_path)


@pytest.mark.slow
class TestBigTextParallelVsSequentialTiming:
    """Demonstrate why asyncio parallelism matters for many chunks (simulated I/O latency)."""

    async def test_parallel_wall_clock_beats_sequential(self, tmp_path):
        """Many chunks × fixed async sleep: parallel=1 ~ n×sleep; parallel=8 ~ ⌈n/8⌉×sleep."""
        n_chunks = 20
        per_chunk_sleep = 0.04
        chunks = [f"paragraph {i} " + ("word " * 40) for i in range(n_chunks)]
        output_path = str(tmp_path / "out.mp3")

        async def fake_io_bound_generate(text, language, out_path, quiet=False, **kwargs):
            await asyncio.sleep(per_chunk_sleep)
            with open(out_path, "wb") as f:
                f.write(b"\x00")
            return True

        mock_progress = MagicMock()
        cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch("TTS_ka.ultra_fast.fast_generate_audio", new=fake_io_bound_generate), \
                 patch("TTS_ka.ultra_fast.create_progress_display", return_value=mock_progress):
                t0 = time.perf_counter()
                await ultra_fast_parallel_generation(
                    chunks, "en", parallel=1, output_path=output_path
                )
                t_sequential = time.perf_counter() - t0

                for p in tmp_path.glob(".part_*.mp3"):
                    p.unlink(missing_ok=True)

                t0 = time.perf_counter()
                await ultra_fast_parallel_generation(
                    chunks, "en", parallel=8, output_path=output_path
                )
                t_parallel = time.perf_counter() - t0
        finally:
            os.chdir(cwd)

        assert t_parallel < t_sequential * 0.55, (
            f"expected parallel (workers=8) wall time << sequential (workers=1); "
            f"got parallel={t_parallel:.3f}s vs sequential={t_sequential:.3f}s"
        )


class TestStreamingFallback:
    """BUG-3: --stream falls back gracefully when VLC (or any player) is missing."""

    async def test_stream_with_mpv_player(self, tmp_path, capsys):
        """When mpv is the detected player, streaming preserves show_gui as passed."""
        output_path = str(tmp_path / "out.mp3")
        text = "word " * 300
        captured_show_gui = {}

        def fake_player_ctor(show_gui=True, preferred=None):
            captured_show_gui['value'] = show_gui
            inst = MagicMock()
            return inst

        with patch('TTS_ka.streaming_player.PlayerDetector.find',
                   return_value="/usr/bin/mpv"), \
             patch('TTS_ka.ultra_fast.StreamingAudioPlayer',
                   side_effect=fake_player_ctor), \
             patch('TTS_ka.ultra_fast.ultra_fast_parallel_generation',
                   new=AsyncMock(return_value=[output_path])), \
             patch('TTS_ka.ultra_fast.fast_merge_audio_files'), \
             patch('TTS_ka.ultra_fast.create_progress_display',
                   return_value=MagicMock()):
            await smart_generate_long_text(text, "en", chunk_seconds=20, parallel=2,
                                           output_path=output_path,
                                           enable_streaming=True, show_gui=True)

        # mpv is the primary player — show_gui is passed through unchanged
        # (mpv supports GUI playback via --force-window)
        assert captured_show_gui['value'] is True
        err = capsys.readouterr().err
        assert "Streaming enabled" in err

    async def test_stream_no_player_still_generates_file(self, tmp_path, capsys):
        """No audio player at all -> warn, but generation proceeds."""
        output_path = str(tmp_path / "out.mp3")
        text = "word " * 300

        with patch('TTS_ka.streaming_player.PlayerDetector.find',
                   return_value=None), \
             patch('TTS_ka.ultra_fast.StreamingAudioPlayer') as msp_cls, \
             patch('TTS_ka.ultra_fast.ultra_fast_parallel_generation',
                   new=AsyncMock(return_value=[output_path])) as mupg, \
             patch('TTS_ka.ultra_fast.fast_merge_audio_files'), \
             patch('TTS_ka.ultra_fast.create_progress_display',
                   return_value=MagicMock()):
            await smart_generate_long_text(text, "en", chunk_seconds=20, parallel=2,
                                           output_path=output_path,
                                           enable_streaming=True, show_gui=True)

        # Generation must have run
        mupg.assert_called_once()
        # Player was constructed with show_gui forced to False
        msp_cls.assert_called_once()
        assert msp_cls.call_args.kwargs.get('show_gui') is False
        err = capsys.readouterr().err
        assert "media player" in err.lower()

    async def test_stream_does_not_raise_systemexit(self, tmp_path):
        """The old SystemExit(1) path must NOT be reached when VLC is missing."""
        output_path = str(tmp_path / "out.mp3")
        text = "word " * 300

        with patch('TTS_ka.streaming_player.PlayerDetector.find',
                   return_value=None), \
             patch('TTS_ka.ultra_fast.StreamingAudioPlayer') as msp_cls, \
             patch('TTS_ka.ultra_fast.ultra_fast_parallel_generation',
                   new=AsyncMock(return_value=[output_path])), \
             patch('TTS_ka.ultra_fast.fast_merge_audio_files'), \
             patch('TTS_ka.ultra_fast.create_progress_display',
                   return_value=MagicMock()):
            # Should complete without raising SystemExit
            await smart_generate_long_text(text, "en", chunk_seconds=20, parallel=2,
                                           output_path=output_path,
                                           enable_streaming=True, show_gui=True)
        msp_cls.assert_called_once()

    async def test_preferred_player_passed_to_detector(self, tmp_path):
        """preferred_player is forwarded to PlayerDetector.find()."""
        output_path = str(tmp_path / "out.mp3")
        text = "word " * 300

        with patch('TTS_ka.streaming_player.PlayerDetector.find',
                   return_value="/usr/bin/mpv") as mfind, \
             patch('TTS_ka.ultra_fast.StreamingAudioPlayer'), \
             patch('TTS_ka.ultra_fast.ultra_fast_parallel_generation',
                   new=AsyncMock(return_value=[output_path])), \
             patch('TTS_ka.ultra_fast.fast_merge_audio_files'), \
             patch('TTS_ka.ultra_fast.create_progress_display',
                   return_value=MagicMock()):
            await smart_generate_long_text(text, "en", chunk_seconds=20, parallel=2,
                                           output_path=output_path,
                                           enable_streaming=True, show_gui=False,
                                           preferred_player="mpv")
        mfind.assert_called_with(preferred="mpv")

    async def test_streaming_uses_fast_first_chunk(self, tmp_path):
        """Streaming carves a small lead-in first chunk for lower latency."""
        from TTS_ka.constants import STREAMING_FIRST_CHUNK_SECONDS
        output_path = str(tmp_path / "out.mp3")
        captured = {}

        def fake_split(t, approx_seconds=60, first_chunk_seconds=0):
            captured['first'] = first_chunk_seconds
            return ["a", "b", "c"]

        with patch('TTS_ka.chunking.split_text_into_chunks', side_effect=fake_split), \
             patch('TTS_ka.streaming_player.PlayerDetector.find',
                   return_value="/usr/bin/mpv"), \
             patch('TTS_ka.ultra_fast.StreamingAudioPlayer'), \
             patch('TTS_ka.ultra_fast.ultra_fast_parallel_generation',
                   new=AsyncMock(return_value=[output_path])), \
             patch('TTS_ka.ultra_fast.fast_merge_audio_files'), \
             patch('TTS_ka.ultra_fast.create_progress_display',
                   return_value=MagicMock()):
            await smart_generate_long_text(
                "word " * 300, "en", chunk_seconds=20, parallel=2,
                output_path=output_path, enable_streaming=True, show_gui=True)

        assert captured['first'] == STREAMING_FIRST_CHUNK_SECONDS
        assert STREAMING_FIRST_CHUNK_SECONDS > 0

    async def test_non_streaming_keeps_uniform_chunks(self, tmp_path):
        """Without streaming, no special first chunk (first_chunk_seconds == 0)."""
        output_path = str(tmp_path / "out.mp3")
        captured = {}

        def fake_split(t, approx_seconds=60, first_chunk_seconds=0):
            captured['first'] = first_chunk_seconds
            return ["a", "b", "c"]

        with patch('TTS_ka.chunking.split_text_into_chunks', side_effect=fake_split), \
             patch('TTS_ka.ultra_fast.ultra_fast_parallel_generation',
                   new=AsyncMock(return_value=[output_path])), \
             patch('TTS_ka.ultra_fast.fast_merge_audio_files'), \
             patch('TTS_ka.ultra_fast.create_progress_display',
                   return_value=MagicMock()):
            await smart_generate_long_text(
                "word " * 300, "en", chunk_seconds=20, parallel=2,
                output_path=output_path, enable_streaming=False)

        assert captured['first'] == 0


class TestPlayerDetectorPreferred:
    """BUG-3 supporting: PlayerDetector.find(preferred=...)."""

    def test_preferred_player_tried_first(self):
        """When preferred is set, it's at the head of the candidate list."""
        from TTS_ka.streaming_player import PlayerDetector
        with patch.object(PlayerDetector, '_locate', return_value=None) as mloc:
            PlayerDetector.find(preferred="mpv")
        first_call_arg = mloc.call_args_list[0].args[0]
        assert first_call_arg == "mpv"

    def test_no_preferred_uses_default_order(self):
        """Without preferred, the first candidate tried is mpv (highest priority player)."""
        from TTS_ka.streaming_player import PlayerDetector
        with patch.object(PlayerDetector, '_locate', return_value=None) as mloc:
            PlayerDetector.find()
        assert mloc.call_args_list[0].args[0] == "mpv"

    def test_preferred_returned_when_found(self):
        """When the preferred player is available, return its path."""
        from TTS_ka.streaming_player import PlayerDetector
        def locate(name):
            return "/usr/bin/" + name if name == "mpv" else None
        with patch.object(PlayerDetector, '_locate', side_effect=locate):
            result = PlayerDetector.find(preferred="mpv")
        assert result == "/usr/bin/mpv"


class TestRunDirs:
    @staticmethod
    async def _fake_generate(text, lang, output, quiet=False, **kwargs):
        with open(output, "wb") as f:
            f.write(b"\xff\xf3" + text.encode())
        return True

    async def test_parts_stay_out_of_cwd_and_run_dir_is_removed(self, tmp_path, monkeypatch):
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        out = cwd / "out.mp3"
        with patch('TTS_ka.ultra_fast._make_run_dir', return_value=str(run_dir)), \
             patch('TTS_ka.ultra_fast.fast_generate_audio', new=self._fake_generate):
            await smart_generate_long_text("word " * 300, "en", chunk_seconds=20,
                                           parallel=2, output_path=str(out))
        assert out.read_bytes().startswith(b"\xff\xf3word")
        assert not run_dir.exists()
        assert [p.name for p in cwd.iterdir()] == ["out.mp3"]

    async def test_merge_failure_raises_and_removes_run_dir(self, tmp_path):
        from TTS_ka.fast_audio import MergeFailed
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        out = tmp_path / "out.mp3"
        player = MagicMock()
        with patch('TTS_ka.ultra_fast._make_run_dir', return_value=str(run_dir)), \
             patch('TTS_ka.ultra_fast.fast_generate_audio', new=self._fake_generate), \
             patch('TTS_ka.ultra_fast.fast_merge_audio_files', side_effect=MergeFailed("boom")), \
             patch('TTS_ka.streaming_player.PlayerDetector.find', return_value="mpv"), \
             patch('TTS_ka.ultra_fast.StreamingAudioPlayer', return_value=player), \
             patch('TTS_ka.ultra_fast.stop_active_streaming_player') as mstop:
            with pytest.raises(MergeFailed):
                await smart_generate_long_text("word " * 300, "en", chunk_seconds=20,
                                               parallel=2, output_path=str(out),
                                               enable_streaming=True, show_gui=False)
        assert not out.exists()
        assert not run_dir.exists()
        mstop.assert_called_once()

    async def test_stop_during_playback_stops_the_player(self, tmp_path):
        """Stop pressed after generation finished cuts playback short, not just synthesis."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        cancel = threading.Event()
        player = MagicMock()

        def playing(timeout=None, cancel_event=None):
            assert cancel_event is cancel
            cancel.set()  # the user presses Stop mid-playback
            return False

        player.wait_until_released.side_effect = playing
        with patch('TTS_ka.ultra_fast._make_run_dir', return_value=str(run_dir)), \
             patch('TTS_ka.ultra_fast.fast_generate_audio', new=self._fake_generate), \
             patch('TTS_ka.streaming_player.PlayerDetector.find', return_value="mpv"), \
             patch('TTS_ka.ultra_fast.StreamingAudioPlayer', return_value=player), \
             patch('TTS_ka.ultra_fast.stop_active_streaming_player') as mstop:
            with pytest.raises(GenerationCancelled):
                await smart_generate_long_text("word " * 300, "en", chunk_seconds=20,
                                               parallel=2, output_path=str(tmp_path / "out.mp3"),
                                               enable_streaming=True, show_gui=False,
                                               cancel_event=cancel)
        mstop.assert_called_once()
        assert not run_dir.exists()

    async def test_keep_parts_keeps_run_dir(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        with patch('TTS_ka.ultra_fast._make_run_dir', return_value=str(run_dir)), \
             patch('TTS_ka.ultra_fast.fast_generate_audio', new=self._fake_generate):
            await smart_generate_long_text("word " * 300, "en", chunk_seconds=20, parallel=2,
                                           output_path=str(tmp_path / "out.mp3"), keep_parts=True)
        assert sorted(p.name for p in run_dir.iterdir())[0] == ".part_0000.mp3"

    async def test_empty_after_sanitizing_raises_empty_input_error(self, tmp_path):
        from TTS_ka.ultra_fast import EmptyInputError
        with pytest.raises(EmptyInputError):
            await smart_generate_long_text("   ", "en", output_path=str(tmp_path / "o.mp3"))

    def test_sweep_removes_only_stale_run_dirs(self, tmp_path):
        from TTS_ka.ultra_fast import RUN_DIR_PREFIX, _sweep_stale_run_dirs
        stale = tmp_path / f"{RUN_DIR_PREFIX}old"
        fresh = tmp_path / f"{RUN_DIR_PREFIX}new"
        other = tmp_path / "unrelated-old"
        for d in (stale, fresh, other):
            d.mkdir()
            (d / ".part_0000.mp3").write_bytes(b"x")
        old = time.time() - 13 * 3600
        os.utime(stale, (old, old))
        os.utime(other, (old, old))
        with patch('TTS_ka.ultra_fast.tempfile.gettempdir', return_value=str(tmp_path)):
            _sweep_stale_run_dirs()
        assert not stale.exists()
        assert fresh.exists() and other.exists()


class TestFailFastAndResume:
    async def test_first_failure_cancels_remaining_chunks(self, tmp_path):
        release = asyncio.Event()
        cancelled = []

        async def gen(text, lang, output, quiet=False, **kwargs):
            if text == "bad":
                return False
            try:
                await release.wait()
            except asyncio.CancelledError:
                cancelled.append(text)
                raise
            return True

        with patch('TTS_ka.ultra_fast.fast_generate_audio', new=gen), \
             patch('TTS_ka.ultra_fast.create_progress_display', return_value=MagicMock()):
            with pytest.raises(GenerationFailed, match="1 of 3 chunks failed"):
                await asyncio.wait_for(ultra_fast_parallel_generation(
                    ["slow one", "bad", "slow two"], "en", parallel=3,
                    output_path=str(tmp_path / "o.mp3"), work_dir=str(tmp_path)), timeout=2)
        assert sorted(cancelled) == ["slow one", "slow two"]

    async def test_rerun_after_failure_only_synthesizes_missing_chunks(self, tmp_path, monkeypatch):
        """Finished chunks land in the cache, so a re-run resumes instead of starting over."""
        from TTS_ka import chunk_cache
        monkeypatch.setenv("TTS_KA_CACHE", "1")
        monkeypatch.setenv("TTS_KA_CACHE_DIR", str(tmp_path / "cache"))
        chunk_cache.configure()
        synthesized = []
        fail_on = {"chunk two"}

        class FakeCommunicate:
            def __init__(self, text, voice, **kwargs):
                self.text = text

            async def save(self, path):
                if self.text in fail_on:
                    raise ValueError("service hiccup")
                synthesized.append(self.text)
                with open(path, "wb") as f:
                    f.write(b"\xff\xf3" + self.text.encode())

        chunks = ["chunk one", "chunk two", "chunk three"]
        (tmp_path / "run1").mkdir()
        with patch.dict('sys.modules', {'edge_tts': MagicMock(Communicate=FakeCommunicate)}), \
             patch('TTS_ka.ultra_fast.create_progress_display', return_value=MagicMock()):
            with pytest.raises(GenerationFailed):
                await ultra_fast_parallel_generation(chunks, "en", parallel=1,
                                                     work_dir=str(tmp_path / "run1"))
            first = list(synthesized)
            fail_on.clear()
            synthesized.clear()
            (tmp_path / "run2").mkdir()
            parts = await ultra_fast_parallel_generation(chunks, "en", parallel=1,
                                                         work_dir=str(tmp_path / "run2"))
        assert "chunk one" in first
        assert "chunk one" not in synthesized              # served from cache
        assert "chunk two" in synthesized
        assert [open(p, "rb").read()[2:].decode() for p in parts] == chunks

    def test_worker_cap_is_fixed_not_cpu_scaled(self):
        from TTS_ka.constants import MAX_PARALLEL_WORKERS
        assert OPTIMAL_WORKERS == MAX_PARALLEL_WORKERS == 6
