"""Tests for user_config JSON loading and CLI defaults."""

import json
import os
from unittest.mock import patch

import pytest

from TTS_ka.user_config import (
    apply_env_from_config,
    argparse_defaults_from_config,
    load_user_config,
    merge_hotkey_bindings,
    resolved_playback_flags,
    resolve_config_path,
    write_user_config,
)


class TestLoadUserConfig:
    def test_missing_file_returns_empty(self, tmp_path):
        assert load_user_config(str(tmp_path / "nope.json")) == {}

    def test_valid_json(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text(
            json.dumps({"lang": "ka", "parallel": 4, "no_play": True}),
            encoding="utf-8",
        )
        cfg = load_user_config(str(p))
        assert cfg["lang"] == "ka"
        assert cfg["parallel"] == 4
        assert cfg["no_play"] is True

    def test_invalid_json_returns_empty(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not json", encoding="utf-8")
        assert load_user_config(str(p)) == {}

    def test_non_object_json_returns_empty(self, tmp_path):
        p = tmp_path / "list.json"
        p.write_text("[1, 2]", encoding="utf-8")
        assert load_user_config(str(p)) == {}


class TestArgparseDefaults:
    def test_empty_config_english_defaults(self):
        d = argparse_defaults_from_config({})
        assert d["lang"] == "en"
        assert d["chunk_seconds"] == 0
        assert d["parallel"] == 0
        assert d["output"] == "data.mp3"
        assert d["no_play"] is False
        assert d["stream"] is False

    def test_invalid_lang_falls_back_en(self):
        d = argparse_defaults_from_config({"lang": "xx"})
        assert d["lang"] == "en"

    def test_legacy_key_maps_no_turbo(self):
        d = argparse_defaults_from_config({"legacy": True})
        assert d["no_turbo"] is True


class TestResolvedPlaybackFlags:
    def test_cli_no_play_overrides_config_default(self):
        defaults = argparse_defaults_from_config({"no_play": False})
        args = type("A", (), {"no_play": True})()
        r = resolved_playback_flags(args, defaults)
        assert r["no_play"] is True

    def test_config_no_play_when_cli_absent(self):
        defaults = argparse_defaults_from_config({"no_play": True})
        args = type("A", (), {})()
        assert not hasattr(args, "no_play")
        r = resolved_playback_flags(args, defaults)
        assert r["no_play"] is True


class TestApplyEnvFromConfig:
    def test_sets_skip_http_when_unset(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TTS_KA_SKIP_HTTP", None)
            apply_env_from_config({"skip_http": True})
            assert os.environ.get("TTS_KA_SKIP_HTTP") == "1"

    def test_respects_existing_env(self):
        with patch.dict(os.environ, {"TTS_KA_SKIP_HTTP": "0"}, clear=False):
            apply_env_from_config({"skip_http": True})
            assert os.environ["TTS_KA_SKIP_HTTP"] == "0"


class TestResolveConfigPath:
    def test_explicit_wins(self, tmp_path):
        p = tmp_path / "x.json"
        p.write_text("{}", encoding="utf-8")
        assert resolve_config_path(str(p)) == p


class TestMergeHotkeyBindings:
    def test_overlay_and_remove(self):
        defaults = {"<a>": "en", "<b>": "ru"}
        cfg = {"hotkeys": {"<a>": "ka", "<c>": "en", "<b>": None}}
        m = merge_hotkey_bindings(cfg, defaults)
        assert m["<a>"] == "ka"
        assert "<b>" not in m
        assert m["<c>"] == "en"

    def test_invalid_lang_skipped(self):
        defaults = {"<a>": "en"}
        cfg = {"hotkeys": {"<a>": "not-a-lang"}}
        m = merge_hotkey_bindings(cfg, defaults)
        assert m["<a>"] == "en"

    def test_non_dict_hotkeys_ignored(self):
        m = merge_hotkey_bindings({"hotkeys": [1, 2]}, {"x": "en"})
        assert m == {"x": "en"}


class TestWriteUserConfig:
    def test_write_then_load_roundtrip(self, tmp_path):
        p = tmp_path / "out.json"
        write_user_config(
            p,
            {
                "lang": "ka",
                "output": "speech.mp3",
                "chunk_seconds": 30,
                "parallel": 2,
                "no_play": True,
            },
        )
        cfg = load_user_config(str(p))
        assert cfg["lang"] == "ka"
        assert cfg["output"] == "speech.mp3"
        assert cfg["chunk_seconds"] == 30
        assert cfg["parallel"] == 2
        assert cfg["no_play"] is True
