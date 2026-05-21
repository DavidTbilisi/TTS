"""BUG-5: layered defaults from env-vars and JSON config file."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from TTS_ka.config import load_settings


class TestLoadSettings:
    """Direct tests of load_settings(): file + env layering and validation."""

    def test_no_env_no_files_returns_builtin_defaults(self, tmp_path):
        result = load_settings(env={}, config_paths=[tmp_path / "missing.json"])
        assert result["lang"] == "en"
        assert result["turbo"] is True
        assert result["auto_play"] is True

    def test_env_var_overrides_builtin_default(self):
        result = load_settings(env={"TTS_DEFAULT_LANG": "ru"}, config_paths=[])
        assert result["lang"] == "ru"

    def test_env_var_invalid_lang_is_dropped_with_warning(self, capsys):
        result = load_settings(env={"TTS_DEFAULT_LANG": "zz"}, config_paths=[])
        assert result["lang"] == "en"  # fell back to built-in
        assert "invalid env value" in capsys.readouterr().err

    def test_config_file_loaded_from_xdg_then_dotfile(self, tmp_path):
        xdg = tmp_path / "TTS_ka" / "config.json"
        xdg.parent.mkdir(parents=True)
        xdg.write_text(json.dumps({"default_lang": "ka"}), encoding="utf-8")
        result = load_settings(env={}, config_paths=[xdg])
        assert result["lang"] == "ka"

    def test_env_overrides_config_file(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"default_lang": "ka"}), encoding="utf-8")
        result = load_settings(
            env={"TTS_DEFAULT_LANG": "ru"},
            config_paths=[cfg],
        )
        assert result["lang"] == "ru"  # env wins over file

    def test_malformed_json_warns_and_uses_defaults(self, tmp_path, capsys):
        cfg = tmp_path / "config.json"
        cfg.write_text("{not json", encoding="utf-8")
        result = load_settings(env={}, config_paths=[cfg])
        assert result["lang"] == "en"
        err = capsys.readouterr().err
        assert "malformed" in err.lower()

    def test_unknown_config_keys_warn_but_dont_crash(self, tmp_path, capsys):
        cfg = tmp_path / "config.json"
        cfg.write_text(
            json.dumps({"spelm": True, "default_lang": "ru"}),
            encoding="utf-8",
        )
        result = load_settings(env={}, config_paths=[cfg])
        assert result["lang"] == "ru"
        assert "spelm" in capsys.readouterr().err

    def test_turbo_mode_truthy_strings(self):
        for raw in ("turbo", "1", "true", "yes", "on"):
            result = load_settings(env={"TTS_DEFAULT_MODE": raw}, config_paths=[])
            assert result["turbo"] is True, raw

    def test_turbo_mode_falsy_string(self):
        result = load_settings(env={"TTS_DEFAULT_MODE": "off"}, config_paths=[])
        assert result["turbo"] is False

    def test_auto_play_from_env(self):
        result = load_settings(env={"TTS_AUTO_PLAY": "false"}, config_paths=[])
        assert result["auto_play"] is False

    def test_parallel_workers_coerced_to_int(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"parallel_workers": 6}), encoding="utf-8")
        result = load_settings(env={}, config_paths=[cfg])
        assert result["parallel"] == 6

    def test_parallel_from_env_str(self):
        result = load_settings(env={"TTS_DEFAULT_PARALLEL": "4"}, config_paths=[])
        assert result["parallel"] == 4

    def test_output_dir_env_var_picked_up(self):
        result = load_settings(env={"TTS_OUTPUT_DIR": "/tmp/audio"}, config_paths=[])
        assert result["output_dir"] == "/tmp/audio"

    def test_non_object_json_warns(self, tmp_path, capsys):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        result = load_settings(env={}, config_paths=[cfg])
        assert result["lang"] == "en"  # ignored bad file
        assert "JSON object" in capsys.readouterr().err


class TestPrecedenceIntegration:
    """End-to-end precedence: CLI > env > config > built-in."""

    def _run_main(self, argv):
        with patch("sys.argv", argv):
            with patch("TTS_ka.main.fast_generate_audio",
                       new=AsyncMock(return_value=True)) as mfa, \
                 patch("TTS_ka.main.cleanup_http", new=AsyncMock()), \
                 patch("TTS_ka.main.get_optimal_settings",
                       return_value={"method": "direct", "chunk_seconds": 0, "parallel": 1}):
                from TTS_ka.main import main
                main()
        return mfa

    def test_env_lang_used_when_no_cli_flag(self):
        with patch("TTS_ka.main.load_settings",
                   return_value={"lang": "ru", "turbo": True, "auto_play": True,
                                 "chunk_seconds": 0, "parallel": 0,
                                 "output": None, "output_dir": None, "player": None}):
            mfa = self._run_main(["TTS_ka", "Привет", "--no-play"])
        # second positional arg of fast_generate_audio is the language
        args, _ = mfa.call_args
        assert args[1] == "ru"

    def test_cli_flag_overrides_env(self):
        with patch("TTS_ka.main.load_settings",
                   return_value={"lang": "ru", "turbo": True, "auto_play": True,
                                 "chunk_seconds": 0, "parallel": 0,
                                 "output": None, "output_dir": None, "player": None}):
            mfa = self._run_main(["TTS_ka", "Hello", "--lang", "en", "--no-play"])
        args, _ = mfa.call_args
        assert args[1] == "en"

    def test_config_auto_play_false_skips_playback(self):
        with patch("TTS_ka.main.load_settings",
                   return_value={"lang": "en", "turbo": True, "auto_play": False,
                                 "chunk_seconds": 0, "parallel": 0,
                                 "output": None, "output_dir": None, "player": None}), \
             patch("sys.argv", ["TTS_ka", "Hello"]), \
             patch("TTS_ka.main.fast_generate_audio",
                   new=AsyncMock(return_value=True)), \
             patch("TTS_ka.main.cleanup_http", new=AsyncMock()), \
             patch("TTS_ka.main.play_audio") as mpa, \
             patch("TTS_ka.main.get_optimal_settings",
                   return_value={"method": "direct", "chunk_seconds": 0, "parallel": 1}):
            from TTS_ka.main import main
            main()
        mpa.assert_not_called()

    def test_output_dir_env_creates_default_in_that_dir(self, tmp_path):
        out_dir = tmp_path / "audio"
        with patch("TTS_ka.main.load_settings",
                   return_value={"lang": "en", "turbo": True, "auto_play": True,
                                 "chunk_seconds": 0, "parallel": 0,
                                 "output": None, "output_dir": str(out_dir),
                                 "player": None}):
            mfa = self._run_main(["TTS_ka", "Hi", "--no-play"])
        args, _ = mfa.call_args
        expected = str(out_dir / "data.mp3").replace("\\", "/")
        assert args[2].replace("\\", "/") == expected
        # The parent dir was auto-created
        assert out_dir.is_dir()
