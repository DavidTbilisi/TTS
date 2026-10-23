"""FEAT-8: shell-completion script generation for bash / zsh / fish."""

from __future__ import annotations

import shutil
import subprocess
from unittest.mock import patch

import pytest

from TTS_ka import completion


class TestBashCompletion:
    def test_contains_compgen_and_complete_directive(self):
        out = completion.bash_completion()
        assert "compgen" in out
        assert "complete -F" in out

    def test_lang_choices_present(self):
        out = completion.bash_completion()
        assert 'compgen -W "ka ka-m ru en en-US"' in out

    @pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
    def test_registers_both_command_spellings(self, shell):
        out = completion.render(shell)
        assert "tts-ka" in out
        assert "TTS_ka" in out
        for flag in ("live", "doctor", "config", "chunk-seconds"):
            assert (f"-l {flag}" if shell == "fish" else f"--{flag}") in out

    def test_voice_ids_present(self):
        out = completion.bash_completion()
        assert "en-US-JennyNeural" in out
        assert "ka-GE-EkaNeural" in out

    @pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
    def test_bash_n_lint_passes(self):
        """`bash -n` (no-execute syntax check) accepts the generated script."""
        script = completion.bash_completion()
        result = subprocess.run(
            ["bash", "-n", "-c", script],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


class TestZshCompletion:
    def test_starts_with_compdef_directive(self):
        out = completion.zsh_completion()
        # The header (#compdef TTS_ka) must be the first non-empty line.
        first_line = next(line for line in out.splitlines() if line.strip())
        assert first_line == "#compdef tts-ka TTS_ka"

    def test_voice_ids_present(self):
        out = completion.zsh_completion()
        assert "en-US-JennyNeural" in out

    def test_uses_arguments_for_parsing(self):
        out = completion.zsh_completion()
        assert "_arguments" in out


class TestFishCompletion:
    def test_uses_complete_directive(self):
        out = completion.fish_completion()
        for line in out.strip().splitlines():
            assert line.startswith(("complete -c tts-ka ", "complete -c TTS_ka ")), line

    def test_lang_choices_present(self):
        out = completion.fish_completion()
        assert "-xa 'ka ka-m ru en en-US'" in out

    def test_voice_ids_present(self):
        out = completion.fish_completion()
        assert "en-US-JennyNeural" in out


class TestRender:
    def test_render_each_shell(self):
        for shell in ("bash", "zsh", "fish"):
            out = completion.render(shell)
            assert out.strip(), f"{shell} completion empty"

    def test_render_unknown_shell_raises(self):
        with pytest.raises(ValueError):
            completion.render("powershell")


class TestCLIPrintCompletion:
    def test_cli_prints_bash_script_and_exits_zero(self, capsys):
        with patch("sys.argv", ["TTS_ka", "--print-completion", "bash"]):
            from TTS_ka.main import main
            main()
        out = capsys.readouterr().out
        assert "complete -F" in out
        assert "TTS_ka" in out

    def test_cli_prints_zsh_script(self, capsys):
        with patch("sys.argv", ["TTS_ka", "--print-completion", "zsh"]):
            from TTS_ka.main import main
            main()
        out = capsys.readouterr().out
        assert out.startswith("#compdef")

    def test_cli_prints_fish_script(self, capsys):
        with patch("sys.argv", ["TTS_ka", "--print-completion", "fish"]):
            from TTS_ka.main import main
            main()
        out = capsys.readouterr().out
        assert "complete -c TTS_ka" in out
