"""Windows shell helper (context menu script discovery)."""

from __future__ import annotations

from TTS_ka.windows_shell import find_context_menu_installer


def test_find_installer_in_repo_layout(tmp_path) -> None:
    repo = tmp_path / "repo"
    script = repo / "extras" / "windows" / "context_menu" / "Install-TTS_ka-ContextMenu.ps1"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("# stub", encoding="utf-8")
    pkg = repo / "src" / "TTS_ka"
    pkg.mkdir(parents=True, exist_ok=True)
    got = find_context_menu_installer(pkg)
    assert got == script


def test_find_installer_missing_returns_none(tmp_path) -> None:
    pkg = tmp_path / "empty" / "TTS_ka"
    pkg.mkdir(parents=True, exist_ok=True)
    assert find_context_menu_installer(pkg) is None
