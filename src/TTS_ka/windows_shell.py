"""Locate and run optional Windows Explorer context-menu installer (PowerShell)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_INSTALL_SCRIPT = "Install-TTS_ka-ContextMenu.ps1"


def find_context_menu_installer(start: Path | None = None) -> Path | None:
    """Return path to ``Install-TTS_ka-ContextMenu.ps1`` if found under *start* or its parents.

    Works when running from a git checkout (``extras/windows/context_menu/`` next to ``src/``).
    Not bundled in the PyPI wheel unless that layout is present.
    """
    pkg = Path(start) if start is not None else Path(__file__).resolve().parent
    for base in (pkg, *pkg.parents):
        cand = base / "extras" / "windows" / "context_menu" / _INSTALL_SCRIPT
        if cand.is_file():
            return cand
    return None


def run_context_menu_installer(
    *,
    uninstall: bool = False,
    include_txt_files: bool = False,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    """Run the PowerShell installer. Raises ``FileNotFoundError`` if the script is missing."""
    ps1 = find_context_menu_installer()
    if ps1 is None:
        raise FileNotFoundError(_INSTALL_SCRIPT)
    if sys.platform != "win32":
        raise OSError("Context menu installer is only for Windows")
    cmd: list[str] = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ps1),
    ]
    if uninstall:
        cmd.append("-Uninstall")
    elif include_txt_files:
        cmd.append("-IncludeTextFiles")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
