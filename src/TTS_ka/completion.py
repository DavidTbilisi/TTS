"""Shell-completion script generation for bash, zsh, and fish.

The output is intentionally small and hand-rolled: no runtime dependency on
shtab or argparse-internal introspection. The voice list is pulled from
:mod:`TTS_ka.voices` so completions stay in sync with the catalog.
"""

from __future__ import annotations

from typing import List

from . import voices as _voices
from .constants import VOICE_MAP


_LONG_FLAGS: List[str] = [
    "--help", "--version", "--lang", "--voice", "--rate", "--pitch",
    "--volume", "--output", "--force", "--no-play", "--no-turbo",
    "--stream", "--no-gui", "--player", "--list-voices", "--preview-voice",
    "--json", "--title", "--author", "--album", "--cover", "--chapters",
    "--srt", "--vtt", "--help-full", "--print-completion",
    "--chunk-seconds", "--parallel", "--live", "--live-idle-ms",
    "--doctor", "--config", "--no-cache", "--clear-cache", "--pages",
]
_SHORT_FLAGS: List[str] = ["-h", "-V", "-o", "-l", "-c", "-j", "-n", "-s", "-H"]

# Both console-script spellings (see pyproject.toml [project.scripts]).
_COMMANDS: List[str] = ["tts-ka", "TTS_ka"]

_LANGS: List[str] = list(VOICE_MAP)
_PLAYERS: List[str] = ["vlc", "mpv", "ffplay", "mplayer"]


def _voice_ids() -> List[str]:
    return [v.id for v in _voices.all_voices()]


def bash_completion() -> str:
    """Render a bash completion script. Source it from ~/.bashrc or /etc/bash_completion.d/."""
    flags = " ".join(_LONG_FLAGS + _SHORT_FLAGS)
    langs = " ".join(_LANGS)
    players = " ".join(_PLAYERS)
    voices = " ".join(_voice_ids())
    return f"""# bash completion for TTS_ka
_TTS_ka_complete() {{
    local cur prev
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"
    case "$prev" in
        --lang|-l) COMPREPLY=( $(compgen -W "{langs}" -- "$cur") ); return ;;
        --voice|--preview-voice) COMPREPLY=( $(compgen -W "{voices}" -- "$cur") ); return ;;
        --player) COMPREPLY=( $(compgen -W "{players}" -- "$cur") ); return ;;
        --print-completion) COMPREPLY=( $(compgen -W "bash zsh fish" -- "$cur") ); return ;;
        --config|--output|-o|--chapters|--cover) COMPREPLY=( $(compgen -f -- "$cur") ); return ;;
    esac
    if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "{flags}" -- "$cur") )
    else
        COMPREPLY=( $(compgen -f -- "$cur") )
    fi
}}
complete -F _TTS_ka_complete {" ".join(_COMMANDS)}
"""


def zsh_completion() -> str:
    """Render a zsh completion script. Put it in a directory on $fpath."""
    voices = " ".join(_voice_ids())
    langs = " ".join(_LANGS)
    commands = " ".join(_COMMANDS)
    return f"""#compdef {commands}
_TTS_ka() {{
    local -a flags
    flags=(
        '--lang[Language]:lang:({langs})'
        '-l[Language]:lang:({langs})'
        '--voice[Voice ID]:voice:({voices})'
        '--preview-voice[Preview a voice]:voice:({voices})'
        '--player[Streaming player]:player:(vlc mpv ffplay mplayer)'
        '--print-completion[Shell]:shell:(bash zsh fish)'
        '--rate[Speech rate, e.g. +30%%]:rate:'
        '--pitch[Pitch shift, e.g. -2Hz]:pitch:'
        '--volume[Volume, e.g. +10%%]:volume:'
        '--output[Output MP3]:file:_files'
        '-o[Output MP3]:file:_files'
        '--pages[PDF pages, e.g. 20-24]:pages:'
        '--chapters[Chapters JSON]:file:_files'
        '--cover[Cover image]:file:_files'
        '--title[ID3 title]:title:'
        '--author[ID3 author]:author:'
        '--album[ID3 album]:album:'
        '--force[Overwrite existing output]'
        '--no-play[Skip playback]'
        '--no-turbo[Disable auto-optimization]'
        '--stream[Enable streaming playback]'
        '-s[Enable streaming playback]'
        '-n[Skip playback]'
        '--chunk-seconds[Chunk size in seconds]:seconds:'
        '-c[Chunk size in seconds]:seconds:'
        '--parallel[Parallel workers]:workers:'
        '-j[Parallel workers]:workers:'
        '--live[Speak stdin sentence by sentence]'
        '--live-idle-ms[Idle flush delay (ms)]:ms:'
        '--config[Config JSON]:file:_files'
        '--doctor[Check dependencies]'
        '-H[Comprehensive help]'
        '--no-gui[Headless streaming]'
        '--list-voices[List voices]'
        '--json[JSON output]'
        '--srt[Write SRT subtitles]'
        '--vtt[Write VTT subtitles]'
        '--help-full[Comprehensive help]'
        '--version[Print version]'
        '-V[Print version]'
        '--help[Show help]'
        '-h[Show help]'
    )
    _arguments -s $flags '*:file:_files'
}}
compdef _TTS_ka {commands}
"""


def fish_completion() -> str:
    """Render a fish completion script (~/.config/fish/completions/tts-ka.fish)."""
    voices = " ".join(_voice_ids())
    lines = [
        line
        for cmd in _COMMANDS
        for line in (
            f"complete -c {cmd} -l lang -s l -d 'Language' -xa '{' '.join(_LANGS)}'",
            f"complete -c {cmd} -l voice -d 'Voice ID' -xa '{voices}'",
            f"complete -c {cmd} -l preview-voice -d 'Preview a voice' -xa '{voices}'",
            f"complete -c {cmd} -l player -d 'Streaming player' -xa '{' '.join(_PLAYERS)}'",
            f"complete -c {cmd} -l print-completion -d 'Shell' -xa 'bash zsh fish'",
            f"complete -c {cmd} -l rate -d 'Speech rate, e.g. +30%' -r",
            f"complete -c {cmd} -l pitch -d 'Pitch shift, e.g. -2Hz' -r",
            f"complete -c {cmd} -l volume -d 'Volume, e.g. +10%' -r",
            f"complete -c {cmd} -l output -d 'Output MP3' -r",
            f"complete -c {cmd} -s o -d 'Output MP3' -r",
            f"complete -c {cmd} -l pages -d 'PDF pages, e.g. 20-24' -x",
            f"complete -c {cmd} -l chapters -d 'Chapters JSON' -r",
            f"complete -c {cmd} -l cover -d 'Cover image' -r",
            f"complete -c {cmd} -l title -d 'ID3 title' -r",
            f"complete -c {cmd} -l author -d 'ID3 author' -r",
            f"complete -c {cmd} -l album -d 'ID3 album' -r",
            f"complete -c {cmd} -l force -d 'Overwrite existing'",
            f"complete -c {cmd} -l no-play -d 'Skip playback'",
            f"complete -c {cmd} -l no-turbo -d 'Disable auto-opt'",
            f"complete -c {cmd} -l stream -s s -d 'Streaming playback'",
            f"complete -c {cmd} -s n -d 'Skip playback'",
            f"complete -c {cmd} -l chunk-seconds -s c -d 'Chunk size (seconds)' -r",
            f"complete -c {cmd} -l parallel -s j -d 'Parallel workers' -r",
            f"complete -c {cmd} -l live -d 'Speak stdin sentence by sentence'",
            f"complete -c {cmd} -l live-idle-ms -d 'Idle flush delay (ms)' -r",
            f"complete -c {cmd} -l config -d 'Config JSON' -r",
            f"complete -c {cmd} -l doctor -d 'Check dependencies'",
            f"complete -c {cmd} -s H -d 'Comprehensive help'",
            f"complete -c {cmd} -l no-gui -d 'Headless streaming'",
            f"complete -c {cmd} -l list-voices -d 'List voices'",
            f"complete -c {cmd} -l json -d 'JSON output'",
            f"complete -c {cmd} -l srt -d 'Write SRT'",
            f"complete -c {cmd} -l vtt -d 'Write VTT'",
            f"complete -c {cmd} -l help-full -d 'Comprehensive help'",
            f"complete -c {cmd} -l version -d 'Print version'",
            f"complete -c {cmd} -s V -d 'Print version'",
            f"complete -c {cmd} -l help -d 'Show help'",
            f"complete -c {cmd} -s h -d 'Show help'",
        )
    ]
    return "\n".join(lines) + "\n"


GENERATORS = {
    "bash": bash_completion,
    "zsh":  zsh_completion,
    "fish": fish_completion,
}


def render(shell: str) -> str:
    """Render the completion script for *shell* (bash, zsh, or fish)."""
    gen = GENERATORS.get(shell)
    if gen is None:
        raise ValueError(f"unsupported shell: {shell!r} (try bash, zsh, or fish)")
    return gen()
