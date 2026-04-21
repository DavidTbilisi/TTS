"""Tests for ultra_fast module."""

import asyncio
import os
import time

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from TTS_ka.ultra_fast import (
    ultra_fast_parallel_generation,
    ultra_fast_cleanup_parts,
    smart_generate_long_text,
    get_optimal_settings,
    OPTIMAL_WORKERS,
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
    async def test_success_returns_parts(self, tmp_path):
        chunks = ["Hello world", "Second chunk"]
        output_path = str(tmp_path / "out.mp3")

        with patch('TTS_ka.ultra_fast.fast_generate_audio', new=AsyncMock(return_value=True)), \
             patch('TTS_ka.ultra_fast.create_progress_display') as mock_cpd:
            mock_display = MagicMock()
            mock_cpd.return_value = mock_display
            parts = await ultra_fast_parallel_generation(chunks, "en", parallel=2, output_path=output_path)

        assert len(parts) == 2

    async def test_failure_returns_parts_still(self, tmp_path):
        chunks = ["chunk one"]
        output_path = str(tmp_path / "out.mp3")

        with patch('TTS_ka.ultra_fast.fast_generate_audio', new=AsyncMock(return_value=False)), \
             patch('TTS_ka.ultra_fast.create_progress_display', return_value=MagicMock()):
            parts = await ultra_fast_parallel_generation(chunks, "en", parallel=1, output_path=output_path)

        assert isinstance(parts, list)

    async def test_first_chunk_uses_output_path_when_streaming(self, tmp_path):
        chunks = ["chunk one", "chunk two"]
        output_path = str(tmp_path / "out.mp3")
        mock_player = MagicMock()
        mock_player.add_chunk = MagicMock()

        with patch('TTS_ka.ultra_fast.fast_generate_audio', new=AsyncMock(return_value=True)), \
             patch('TTS_ka.ultra_fast.create_progress_display', return_value=MagicMock()):
            parts = await ultra_fast_parallel_generation(
                chunks, "en", parallel=2, streaming_player=mock_player, output_path=output_path
            )

        assert parts[0] == output_path

    async def test_exception_in_worker_caught(self, tmp_path, capsys):
        chunks = ["bad chunk"]
        output_path = str(tmp_path / "out.mp3")

        with patch('TTS_ka.ultra_fast.fast_generate_audio', new=AsyncMock(side_effect=Exception("oops"))), \
             patch('TTS_ka.ultra_fast.create_progress_display', return_value=MagicMock()):
            parts = await ultra_fast_parallel_generation(chunks, "en", parallel=1, output_path=output_path)

        # Error is caught, warning is printed
        assert "oops" in capsys.readouterr().out


class TestSmartGenerateLongText:
    async def test_short_text_direct_generation(self, tmp_path, capsys):
        """Very short text (< 200 words, no streaming) goes direct."""
        output_path = str(tmp_path / "out.mp3")
        text = "Hello world"

        with patch('TTS_ka.ultra_fast.fast_generate_audio', new=AsyncMock(return_value=True)) as mfa:
            await smart_generate_long_text(text, "en", output_path=output_path)

        mfa.assert_called_once()
        assert "direct" in capsys.readouterr().out

    async def test_long_text_uses_chunks(self, tmp_path):
        """Long text is split into chunks and merged."""
        output_path = str(tmp_path / "out.mp3")
        text = "word " * 300

        with patch('TTS_ka.ultra_fast.ultra_fast_parallel_generation', new=AsyncMock(return_value=[output_path])) as mupg, \
             patch('TTS_ka.ultra_fast.fast_merge_audio_files') as mmaf, \
             patch('TTS_ka.ultra_fast.create_progress_display', return_value=MagicMock()):
            await smart_generate_long_text(text, "en", chunk_seconds=20, parallel=2, output_path=output_path)

        mupg.assert_called_once()

    async def test_empty_chunks_raises(self, tmp_path):
        output_path = str(tmp_path / "out.mp3")

        with patch('TTS_ka.chunking.split_text_into_chunks', return_value=[]):
            with pytest.raises(ValueError, match="No text chunks"):
                await smart_generate_long_text("word " * 300, "en", chunk_seconds=20, output_path=output_path)

    @pytest.mark.parametrize("lang", ["ka", "ru", "en"])
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
        # Long-ish strings per chunk (similar to real chunk payloads)
        chunks = [f"paragraph {i} " + ("word " * 40) for i in range(n_chunks)]
        output_path = str(tmp_path / "out.mp3")

        async def fake_io_bound_generate(text, language, out_path, quiet=False):
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

        # Sequential ≈ n·sleep; high parallelism ≈ ⌈n/p⌉·sleep (+ overhead).
        assert t_parallel < t_sequential * 0.55, (
            f"expected parallel (workers=8) wall time << sequential (workers=1); "
            f"got parallel={t_parallel:.3f}s vs sequential={t_sequential:.3f}s"
        )
