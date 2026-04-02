"""Tests for parallel module."""

import pytest
import os
from unittest.mock import patch, AsyncMock, MagicMock
from TTS_ka.parallel import generate_chunks_parallel, cleanup_parts


class TestCleanupParts:
    def test_removes_existing_files(self, tmp_path):
        f = tmp_path / "part.mp3"
        f.write_bytes(b"data")
        cleanup_parts([str(f)])
        assert not f.exists()

    def test_skips_nonexistent_files(self):
        cleanup_parts(["/nonexistent/fake.mp3"])  # must not raise

    def test_keep_parts_skips_deletion(self, tmp_path):
        f = tmp_path / "part.mp3"
        f.write_bytes(b"data")
        cleanup_parts([str(f)], keep_parts=True)
        assert f.exists()

    def test_empty_list(self):
        cleanup_parts([])

    def test_removes_multiple_files(self, tmp_path):
        files = []
        for i in range(3):
            f = tmp_path / f"part_{i}.mp3"
            f.write_bytes(b"x")
            files.append(str(f))
        cleanup_parts(files)
        for f in files:
            assert not os.path.exists(f)

    def test_oserror_silenced(self, tmp_path):
        f = tmp_path / "locked.mp3"
        f.write_bytes(b"x")
        with patch('os.remove', side_effect=OSError("locked")):
            cleanup_parts([str(f)])  # must not raise


class TestGenerateChunksParallel:
    async def test_returns_part_paths(self):
        chunks = ["Hello world", "Second chunk"]
        with patch('TTS_ka.parallel.generate_audio', new=AsyncMock(return_value=True)), \
             patch('TTS_ka.parallel.HAS_TQDM', False), \
             patch('os.path.exists', return_value=False):
            parts = await generate_chunks_parallel(chunks, "en", parallel=2)
        assert len(parts) == 2
        assert all(p.endswith(".mp3") for p in parts)

    async def test_single_chunk(self):
        with patch('TTS_ka.parallel.generate_audio', new=AsyncMock(return_value=True)), \
             patch('TTS_ka.parallel.HAS_TQDM', False), \
             patch('os.path.exists', return_value=False):
            parts = await generate_chunks_parallel(["Hello"], "en", parallel=1)
        assert len(parts) == 1

    async def test_worker_exception_caught(self, capsys):
        chunks = ["bad chunk"]
        with patch('TTS_ka.parallel.generate_audio', new=AsyncMock(side_effect=Exception("fail"))), \
             patch('TTS_ka.parallel.HAS_TQDM', False), \
             patch('os.path.exists', return_value=False):
            parts = await generate_chunks_parallel(chunks, "en", parallel=1)
        assert "fail" in capsys.readouterr().out

    async def test_uses_semaphore_limit(self):
        """parallel=1 should still complete all tasks."""
        chunks = ["a", "b", "c"]
        with patch('TTS_ka.parallel.generate_audio', new=AsyncMock(return_value=True)), \
             patch('TTS_ka.parallel.HAS_TQDM', False), \
             patch('os.path.exists', return_value=False):
            parts = await generate_chunks_parallel(chunks, "en", parallel=1)
        assert len(parts) == 3

    async def test_existing_part_files_removed(self, tmp_path):
        old_part = ".part_0.mp3"
        # Create the file so it exists
        open(old_part, 'w').close()
        try:
            with patch('TTS_ka.parallel.generate_audio', new=AsyncMock(return_value=True)), \
                 patch('TTS_ka.parallel.HAS_TQDM', False):
                await generate_chunks_parallel(["hello"], "en", parallel=1)
        finally:
            if os.path.exists(old_part):
                os.remove(old_part)

    async def test_with_tqdm(self):
        chunks = ["Hello", "World"]
        mock_pbar = MagicMock()
        mock_pbar.__enter__ = MagicMock(return_value=mock_pbar)
        mock_pbar.__exit__ = MagicMock(return_value=None)
        with patch('TTS_ka.parallel.generate_audio', new=AsyncMock(return_value=True)), \
             patch('TTS_ka.parallel.HAS_TQDM', True), \
             patch('TTS_ka.parallel.tqdm', return_value=mock_pbar), \
             patch('os.path.exists', return_value=False):
            parts = await generate_chunks_parallel(chunks, "ka", parallel=2)
        assert len(parts) == 2

    @pytest.mark.parametrize("lang", ["ka", "ru", "en"])
    async def test_all_languages(self, lang):
        with patch('TTS_ka.parallel.generate_audio', new=AsyncMock(return_value=True)), \
             patch('TTS_ka.parallel.HAS_TQDM', False), \
             patch('os.path.exists', return_value=False):
            parts = await generate_chunks_parallel(["test"], lang, parallel=1)
        assert len(parts) == 1
