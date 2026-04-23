"""Runtime dependency checks (ffmpeg, players, Python stack)."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class DepRow:
    name: str
    ok: bool
    detail: str


def _check_module(spec: str, import_name: str) -> DepRow:
    """Verify *import_name* is importable (distribution name *spec* for display)."""
    try:
        mod = importlib.import_module(import_name)
        ver = getattr(mod, "__version__", "")
        detail = f"import ok{f' ({ver})' if ver else ''}"
        return DepRow(spec, True, detail)
    except Exception as exc:  # pragma: no cover - import paths vary
        return DepRow(spec, False, str(exc))


def check_ffmpeg() -> DepRow:
    exe = shutil.which("ffmpeg")
    if not exe:
        return DepRow(
            "ffmpeg",
            False,
            "not on PATH - install ffmpeg (required for merging chunks / pydub MP3)",
        )
    try:
        r = subprocess.run(
            [exe, "-version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0:
            return DepRow("ffmpeg", False, f"exit {r.returncode}")
        first = (r.stdout or "").splitlines()[0] if r.stdout else "ok"
        return DepRow("ffmpeg", True, first.strip())
    except (OSError, subprocess.TimeoutExpired) as exc:
        return DepRow("ffmpeg", False, str(exc))


def check_streaming_player() -> DepRow:
    from .streaming_player import PlayerDetector

    path = PlayerDetector.find()
    if path:
        return DepRow("streaming player", True, f"first match: {path}")
    return DepRow(
        "streaming player",
        False,
        "none of vlc, mpv, ffplay, mplayer found - optional unless you use --stream",
    )


def check_soundfile() -> DepRow:
    if importlib.util.find_spec("soundfile") is None:
        return DepRow(
            "soundfile",
            False,
            "optional pip install soundfile - faster merges when available",
        )
    return _check_module("soundfile", "soundfile")


def check_uvloop() -> DepRow:
    if sys.platform.startswith("win"):
        return DepRow("uvloop", True, "n/a on Windows")
    if importlib.util.find_spec("uvloop") is None:
        return DepRow(
            "uvloop",
            False,
            "optional - pip install uvloop for faster asyncio on Linux/macOS",
        )
    return _check_module("uvloop", "uvloop")


def collect_dep_rows() -> List[DepRow]:
    rows: List[DepRow] = []
    rows.append(_check_module("edge-tts", "edge_tts"))
    rows.append(_check_module("pydub", "pydub"))
    rows.append(_check_module("httpx", "httpx"))
    rows.append(check_soundfile())
    rows.append(check_uvloop())
    rows.append(check_ffmpeg())
    rows.append(check_streaming_player())
    return rows


_OPTIONAL_NAMES = frozenset({"soundfile", "uvloop", "streaming player"})


def format_dep_report(rows: Optional[List[DepRow]] = None) -> str:
    rows = rows or collect_dep_rows()
    lines = ["TTS_ka dependency check", "=" * 40]
    w = max(len(r.name) for r in rows) if rows else 10
    for r in rows:
        if r.ok:
            flag = "OK"
        elif r.name in _OPTIONAL_NAMES:
            flag = "opt"
        else:
            flag = "!!"
        lines.append(f"  [{flag}]  {r.name.ljust(w)}  {r.detail}")
    lines.append("")
    lines.append("ffmpeg: required for long/chunked output and reliable MP3 handling.")
    lines.append("streaming player: needed only for --stream (live playback while generating).")
    return "\n".join(lines)


def run_dependency_check() -> int:
    """Print report to stdout; return 0 if critical deps OK, else 1."""
    rows = collect_dep_rows()
    print(format_dep_report(rows))
    critical = ("edge-tts", "pydub", "ffmpeg")
    bad = [r for r in rows if r.name in critical and not r.ok]
    if bad:
        print("Fix the items marked [!!] above, then run again.", file=sys.stderr)
        return 1
    return 0
