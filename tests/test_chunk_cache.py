"""Tests for the content-addressed chunk cache."""

from __future__ import annotations

import os
import time

import pytest

from TTS_ka import chunk_cache
from TTS_ka.chunk_cache import ChunkCache, cache_key
from TTS_ka.prosody import ProsodyOpts
from TTS_ka.subtitles import WordEvent


@pytest.fixture
def cache(tmp_path):
    return ChunkCache(tmp_path / "cache", max_bytes=10 * 1024 * 1024)


def _file(tmp_path, name, data=b"\xff\xf3audio"):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


class TestKey:
    def test_stable(self):
        assert cache_key("hi", "en-GB-SoniaNeural", None) == cache_key("hi", "en-GB-SoniaNeural", None)

    def test_none_prosody_equals_default(self):
        assert cache_key("hi", "v", None) == cache_key("hi", "v", ProsodyOpts())

    @pytest.mark.parametrize("change", [
        ("hi!", "v", ProsodyOpts()),
        ("hi", "w", ProsodyOpts()),
        ("hi", "v", ProsodyOpts(rate="+10%")),
        ("hi", "v", ProsodyOpts(pitch="+5Hz")),
        ("hi", "v", ProsodyOpts(volume="-10%")),
    ])
    def test_every_input_changes_the_key(self, change):
        assert cache_key(*change) != cache_key("hi", "v", ProsodyOpts())


class TestLocation:
    def test_env_override_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TTS_KA_CACHE_DIR", str(tmp_path / "x"))
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
        assert chunk_cache.default_dir() == tmp_path / "x"

    @pytest.mark.skipif(os.name != "posix" or os.uname().sysname == "Darwin", reason="XDG layout")
    def test_xdg_then_home(self, monkeypatch, tmp_path):
        monkeypatch.delenv("TTS_KA_CACHE_DIR", raising=False)
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
        assert chunk_cache.default_dir() == tmp_path / "xdg" / "tts-ka"
        monkeypatch.delenv("XDG_CACHE_HOME")
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        assert chunk_cache.default_dir() == tmp_path / "home" / ".cache" / "tts-ka"


class TestStoreFetch:
    def test_round_trip_is_an_independent_copy(self, cache, tmp_path):
        key = cache_key("hi", "v", None)
        cache.store(key, _file(tmp_path, "src.mp3"))
        dest = tmp_path / "dest.mp3"
        assert cache.fetch(key, str(dest)) is True
        dest.write_bytes(b"tagged in place")
        assert cache.path_for(key).read_bytes() == b"\xff\xf3audio"

    def test_miss(self, cache, tmp_path):
        assert cache.fetch("0" * 64, str(tmp_path / "d.mp3")) is False

    def test_empty_or_missing_source_is_not_stored(self, cache, tmp_path):
        cache.store("a" * 64, _file(tmp_path, "empty.mp3", b""))
        cache.store("b" * 64, str(tmp_path / "missing.mp3"))
        assert cache.usage() == (0, 0)

    def test_store_is_atomic_no_temp_files_left(self, cache, tmp_path):
        key = cache_key("hi", "v", None)
        cache.store(key, _file(tmp_path, "src.mp3"))
        assert [p.name for p in cache.path_for(key).parent.iterdir()] == [f"{key}.mp3"]

    def test_unwritable_root_is_harmless(self, tmp_path):
        blocker = tmp_path / "file"
        blocker.write_text("not a dir")
        cache = ChunkCache(blocker / "cache", max_bytes=1024)
        cache.store("c" * 64, _file(tmp_path, "src.mp3"))  # must not raise
        assert cache.fetch("c" * 64, str(tmp_path / "d.mp3")) is False

    def test_words_sidecar_round_trip(self, cache):
        key = cache_key("hi there", "v", None)
        events = [WordEvent("hi", 0, 100), WordEvent("there", 100, 200)]
        cache.store_words(key, events)
        assert cache.fetch_words(key) == events
        assert cache.fetch_words("d" * 64) is None


class TestMaintenance:
    def test_prune_removes_least_recently_used_first(self, tmp_path):
        cache = ChunkCache(tmp_path / "cache", max_bytes=10 * 1024 * 1024)
        keys = [cache_key(str(i), "v", None) for i in range(3)]
        for i, key in enumerate(keys):
            cache.store(key, _file(tmp_path, f"{i}.mp3", b"x" * 1000))
            os.utime(cache.path_for(key), (time.time() - 100 + i, time.time() - 100 + i))
        cache.fetch(keys[0], str(tmp_path / "touch.mp3"))   # oldest becomes most recent
        cache.max_bytes = 2000
        assert cache.prune(target_ratio=1.0) == 1
        assert not cache.path_for(keys[1]).exists()
        assert cache.path_for(keys[0]).exists() and cache.path_for(keys[2]).exists()

    def test_first_store_of_a_process_enforces_the_cap(self, tmp_path):
        """Earlier runs may have left the cache over its cap; the next write trims it."""
        roomy = ChunkCache(tmp_path / "cache", max_bytes=10**9)
        for i in range(3):
            roomy.store(cache_key(str(i), "v", None), _file(tmp_path, f"{i}.mp3", b"x" * 1000))
        tight = ChunkCache(tmp_path / "cache", max_bytes=2500)
        tight.store(cache_key("new", "v", None), _file(tmp_path, "new.mp3", b"x" * 1000))
        files, size = tight.usage()
        assert size <= 2500 and files == 2
        assert tight.path_for(cache_key("new", "v", None)).exists()

    def test_clear_reports_and_removes(self, cache, tmp_path):
        cache.store(cache_key("a", "v", None), _file(tmp_path, "a.mp3", b"x" * 10))
        cache.store_words(cache_key("a", "v", None), [WordEvent("a", 0, 1)])
        files, size = cache.clear()
        assert files == 2 and size > 10
        assert cache.usage() == (0, 0)


class TestProcessCache:
    def test_disabled_by_env_and_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TTS_KA_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("TTS_KA_CACHE", "1")
        chunk_cache.configure()
        assert chunk_cache.get_cache() is not None
        chunk_cache.configure(enabled=False)
        assert chunk_cache.get_cache() is None
        monkeypatch.setenv("TTS_KA_CACHE", "0")
        chunk_cache.configure()
        assert chunk_cache.get_cache() is None

    def test_max_mb_from_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TTS_KA_CACHE", "1")
        monkeypatch.setenv("TTS_KA_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("TTS_KA_CACHE_MAX_MB", "7")
        chunk_cache.configure()
        assert chunk_cache.get_cache().max_bytes == 7 * 1024 * 1024
