#!/usr/bin/env python3
"""Bump semver, commit, tag, and push — then open GitHub to publish a Release (triggers PyPI).

Usage:
  python scripts/release.py patch|minor|major [--dry-run] [--no-push] [--allow-dirty]

Requires: git, clean working tree (unless --allow-dirty).
Optional: bump2version (``pip install bump2version``) — otherwise this script bumps files itself.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], *, cwd: Path = REPO_ROOT) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def run_out(cmd: list[str], *, cwd: Path = REPO_ROOT) -> str:
    out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True)
    return (out.stdout or "").strip()


def git_dirty() -> bool:
    r = subprocess.run(
        ["git", "diff", "--quiet", "HEAD"],
        cwd=REPO_ROOT,
    )
    return r.returncode != 0


def parse_semver(s: str) -> tuple[int, int, int]:
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", s.strip())
    if not m:
        raise SystemExit(f"Invalid semver: {s!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def bump_tuple(ver: tuple[int, int, int], part: str) -> tuple[int, int, int]:
    major, minor, patch = ver
    if part == "patch":
        return major, minor, patch + 1
    if part == "minor":
        return major, minor + 1, 0
    if part == "major":
        return major + 1, 0, 0
    raise SystemExit(f"Unknown bump part: {part!r}")


def format_ver(t: tuple[int, int, int]) -> str:
    return f"{t[0]}.{t[1]}.{t[2]}"


def read_current_version() -> str:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    if not m:
        raise SystemExit("Could not find version in pyproject.toml")
    return m.group(1)


def bump_files(old: str, new: str, *, dry_run: bool) -> None:
    """Update version in pyproject.toml, .bumpversion.cfg, __init__.py."""
    files: list[tuple[Path, str, str]] = [
        (REPO_ROOT / "pyproject.toml", f'version = "{old}"', f'version = "{new}"'),
        (REPO_ROOT / ".bumpversion.cfg", f"current_version = {old}", f"current_version = {new}"),
        (
            REPO_ROOT / "src" / "TTS_ka" / "__init__.py",
            f'__version__ = "{old}"',
            f'__version__ = "{new}"',
        ),
    ]
    for path, a, b in files:
        text = path.read_text(encoding="utf-8")
        if a not in text:
            raise SystemExit(f"Expected {a!r} in {path.relative_to(REPO_ROOT)}")
        new_text = text.replace(a, b, 1)
        if dry_run:
            print(f"Would update {path.relative_to(REPO_ROOT)}")
        else:
            path.write_text(new_text, encoding="utf-8")
            print(f"Updated {path.relative_to(REPO_ROOT)}")


def try_bumpversion(part: str, *, dry_run: bool) -> bool:
    """Use bump2version/bumpversion if installed (.bumpversion.cfg lists all files)."""
    if dry_run:
        return False
    for mod in ("bumpversion", "bump2version"):
        try:
            run([sys.executable, "-m", mod, part])
            return True
        except subprocess.CalledProcessError:
            continue
    return False


def github_release_url(tag: str) -> str | None:
    try:
        url = run_out(["git", "remote", "get-url", "origin"])
    except subprocess.CalledProcessError:
        return None
    # git@github.com:Owner/Repo.git or https://github.com/Owner/Repo.git
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", url)
    if not m:
        return None
    owner, repo = m.group(1), m.group(2)
    return f"https://github.com/{owner}/{repo}/releases/new?tag={tag}&title={tag}"


def main() -> None:
    ap = argparse.ArgumentParser(description="Version bump, commit, tag, push for GitHub + PyPI release flow.")
    ap.add_argument("part", choices=("patch", "minor", "major"))
    ap.add_argument("--dry-run", action="store_true", help="Print actions only")
    ap.add_argument("--no-push", action="store_true", help="Commit and tag locally but do not push")
    ap.add_argument("--allow-dirty", action="store_true", help="Allow uncommitted changes (use with care)")
    args = ap.parse_args()

    if not (REPO_ROOT / "pyproject.toml").is_file():
        raise SystemExit("Run from repository root (scripts/release.py).")

    if git_dirty() and not args.allow_dirty and not args.dry_run:
        raise SystemExit("Working tree is not clean. Commit or stash, or pass --allow-dirty.")

    current = read_current_version()
    old_t = parse_semver(current)
    new_t = bump_tuple(old_t, args.part)
    new_v = format_ver(new_t)
    tag = f"v{new_v}"

    print(f"Release bump: {current} -> {new_v} (tag {tag})")

    if args.dry_run:
        bump_files(current, new_v, dry_run=True)
        print("Would git add, commit, tag, push (skipped --dry-run)")
        return

    if not try_bumpversion(args.part, dry_run=False):
        bump_files(current, new_v, dry_run=False)

    run(["git", "add", "pyproject.toml", ".bumpversion.cfg", "src/TTS_ka/__init__.py"])
    run(["git", "commit", "-m", f"chore(release): bump version to {new_v}"])
    run(["git", "tag", "-a", tag, "-m", f"Release {new_v}"])

    if not args.no_push:
        branch = run_out(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        run(["git", "push", "origin", branch])
        run(["git", "push", "origin", tag])

    rel = github_release_url(tag)
    print()
    print("Next: publish a GitHub Release for this tag to trigger PyPI upload:")
    if rel:
        print(f"  {rel}")
    else:
        print("  Repo → Releases → Draft a new release → choose tag", tag, "→ Publish release.")


if __name__ == "__main__":
    main()
