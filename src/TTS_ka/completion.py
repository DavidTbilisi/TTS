"""Shell-completion script generation for bash, zsh, and fish.

The output is intentionally small and hand-rolled: no runtime dependency on
shtab or argparse-internal introspection. The voice list is pulled from
:mod:`TTS_ka.voices` so completions stay in sync with the catalog.
"""

from __future__ import annotations

from typing import List

from . import voices as _voices


_LONG_FLAGS: List[str] = [
    "--help", "--version", "--lang", "--voice", "--rate", "--pitch",
    "--volume", "--output", "--force", "--no-play", "--no-turbo",
    "--stream", "--no-gui", "--player", "--list-voices", "--preview-voice",
    "--json", "--title", "--author", "--album", "--cover", "--chapters",
    "--srt", "--vtt", "--help-full", "--print-completion",
]
_SHORT_FLAGS: List[str] = ["-h", "-V", "-o"]

_LANGS: List[str] = ["en", "ka", "ru"]
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
        --lang) COMPREPLY=( $(compgen -W "{langs}" -- "$cur") ); return ;;
        --voice|--preview-voice) COMPREPLY=( $(compgen -W "{voices}" -- "$cur") ); return ;;
        --player) COMPREPLY=( $(compgen -W "{players}" -- "$cur") ); return ;;
        --print-completion) COMPREPLY=( $(compgen -W "bash zsh fish" -- "$cur") ); return ;;
    esac
    if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "{flags}" -- "$cur") )
    else
        COMPREPLY=( $(compgen -f -- "$cur") )
    fi
}}
complete -F _TTS_ka_complete TTS_ka
"""


def zsh_completion() -> str:
    """Render a zsh completion script. Put it in a directory on $fpath."""
    voices = " ".join(_voice_ids())
    return f"""#compdef TTS_ka
_TTS_ka() {{
    local -a flags
    flags=(
        '--lang[Language (ka, ru, en)]:lang:(en ka ru)'
        '--voice[Voice ID]:voice:({voices})'
        '--preview-voice[Preview a voice]:voice:({voices})'
        '--player[Streaming player]:player:(vlc mpv ffplay mplayer)'
        '--print-completion[Shell]:shell:(bash zsh fish)'
        '--rate[Speech rate, e.g. +30%%]:rate:'
        '--pitch[Pitch shift, e.g. -2Hz]:pitch:'
        '--volume[Volume, e.g. +10%%]:volume:'
        '--output[Output MP3]:file:_files'
        '-o[Output MP3]:file:_files'
        '--chapters[Chapters JSON]:file:_files'
        '--cover[Cover image]:file:_files'
        '--title[ID3 title]:title:'
        '--author[ID3 author]:author:'
        '--album[ID3 album]:album:'
        '--force[Overwrite existing output]'
        '--no-play[Skip playback]'
        '--no-turbo[Disable auto-optimization]'
        '--stream[Enable streaming playback]'
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
compdef _TTS_ka TTS_ka
"""


def fish_completion() -> str:
    """Render a fish completion script (~/.config/fish/completions/TTS_ka.fish)."""
    voices = " ".join(_voice_ids())
    lines = [
        f"complete -c TTS_ka -l lang -d 'Language' -xa '{' '.join(_LANGS)}'",
        f"complete -c TTS_ka -l voice -d 'Voice ID' -xa '{voices}'",
        f"complete -c TTS_ka -l preview-voice -d 'Preview a voice' -xa '{voices}'",
        f"complete -c TTS_ka -l player -d 'Streaming player' -xa '{' '.join(_PLAYERS)}'",
        "complete -c TTS_ka -l print-completion -d 'Shell' -xa 'bash zsh fish'",
        "complete -c TTS_ka -l rate -d 'Speech rate, e.g. +30%' -r",
        "complete -c TTS_ka -l pitch -d 'Pitch shift, e.g. -2Hz' -r",
        "complete -c TTS_ka -l volume -d 'Volume, e.g. +10%' -r",
        "complete -c TTS_ka -l output -d 'Output MP3' -r",
        "complete -c TTS_ka -s o -d 'Output MP3' -r",
        "complete -c TTS_ka -l chapters -d 'Chapters JSON' -r",
        "complete -c TTS_ka -l cover -d 'Cover image' -r",
        "complete -c TTS_ka -l title -d 'ID3 title' -r",
        "complete -c TTS_ka -l author -d 'ID3 author' -r",
        "complete -c TTS_ka -l album -d 'ID3 album' -r",
        "complete -c TTS_ka -l force -d 'Overwrite existing'",
        "complete -c TTS_ka -l no-play -d 'Skip playback'",
        "complete -c TTS_ka -l no-turbo -d 'Disable auto-opt'",
        "complete -c TTS_ka -l stream -d 'Streaming playback'",
        "complete -c TTS_ka -l no-gui -d 'Headless streaming'",
        "complete -c TTS_ka -l list-voices -d 'List voices'",
        "complete -c TTS_ka -l json -d 'JSON output'",
        "complete -c TTS_ka -l srt -d 'Write SRT'",
        "complete -c TTS_ka -l vtt -d 'Write VTT'",
        "complete -c TTS_ka -l help-full -d 'Comprehensive help'",
        "complete -c TTS_ka -l version -d 'Print version'",
        "complete -c TTS_ka -s V -d 'Print version'",
        "complete -c TTS_ka -l help -d 'Show help'",
        "complete -c TTS_ka -s h -d 'Show help'",
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
