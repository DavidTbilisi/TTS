<#
.SYNOPSIS
  One-step Windows setup for TTS_ka: context menu + global hotkeys, with
  prerequisite checks so you know what (if anything) is missing.

.DESCRIPTION
  This is a thin orchestrator over the two existing installers:
    - extras\windows\context_menu\Install-TTS_ka-ContextMenu.ps1  (right-click "Read with TTS_ka")
    - extras\autohotkey\Install-TTS_ka-Hotkeys.ps1                (Alt+E/R/X global hotkeys)

  It first verifies that TTS_ka is runnable, then checks for AutoHotkey v2
  (needed only for the hotkeys + in-app selection menu), then runs both
  installers and prints a "what you can do now" summary.

  Run from the repository root:
    powershell -ExecutionPolicy Bypass -File .\extras\windows\Install-TTS_ka-Windows.ps1

.PARAMETER PythonPath
  Path to python.exe, or "python" / "py" if on PATH. Passed to the context-menu installer.

.PARAMETER Languages
  Languages for the context menu (default: en, ru, ka, ka-m). Passed through.

.PARAMETER SkipHotkeys
  Install only the context menu; do not touch the AutoHotkey startup script.

.PARAMETER SkipContextMenu
  Install only the hotkeys; do not register the right-click menu.

.PARAMETER Uninstall
  Remove both the context menu and the hotkeys startup script.

.PARAMETER WhatIf
  Print actions only; do not modify the registry or Startup folder.
#>
param(
    [string]   $PythonPath = "",
    [string[]] $Languages = @(),
    [switch]   $SkipHotkeys,
    [switch]   $SkipContextMenu,
    [switch]   $Uninstall,
    [switch]   $WhatIf
)

$ErrorActionPreference = "Stop"

$RepoRoot   = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$ContextPs1 = Join-Path $PSScriptRoot "context_menu\Install-TTS_ka-ContextMenu.ps1"
$HotkeysPs1 = Join-Path $RepoRoot "extras\autohotkey\Install-TTS_ka-Hotkeys.ps1"

foreach ($p in @($ContextPs1, $HotkeysPs1)) {
    if (-not (Test-Path -LiteralPath $p)) {
        Write-Error "Missing installer: $p (run this from the TTS_ka repo)."
    }
}

function Test-TTSka {
    # True if `tts-ka` console script or `python -m TTS_ka` resolves.
    if (Get-Command "TTS_ka" -ErrorAction SilentlyContinue) { return $true }
    foreach ($py in @("python", "py")) {
        $c = Get-Command $py -ErrorAction SilentlyContinue
        if (-not $c) { continue }
        try {
            & $c.Source -c "import TTS_ka" 2>$null
            if ($LASTEXITCODE -eq 0) { return $true }
        } catch { }
    }
    return $false
}

function Test-AutoHotkeyV2 {
    $names = @("AutoHotkey64.exe", "AutoHotkey32.exe")
    $roots = @(
        "${env:ProgramFiles}\AutoHotkey\v2",
        "${env:ProgramFiles(x86)}\AutoHotkey\v2",
        "${env:LocalAppData}\Programs\AutoHotkey\v2"
    )
    foreach ($r in $roots) {
        foreach ($n in $names) {
            if (Test-Path -LiteralPath (Join-Path $r $n)) { return $true }
        }
    }
    return [bool](Get-Command "AutoHotkey64.exe" -ErrorAction SilentlyContinue)
}

Write-Host "TTS_ka Windows setup"
Write-Host ("=" * 40)

# --- Uninstall path -------------------------------------------------------
if ($Uninstall) {
    if (-not $SkipContextMenu) {
        & $ContextPs1 -Uninstall -WhatIf:$WhatIf
    }
    if (-not $SkipHotkeys) {
        & $HotkeysPs1 -Uninstall -WhatIf:$WhatIf
    }
    Write-Host ""
    Write-Host "Uninstall complete. (AutoHotkey itself is left installed.)"
    exit 0
}

# --- Prerequisite: TTS_ka must be runnable --------------------------------
if (-not (Test-TTSka)) {
    Write-Warning "TTS_ka does not appear to be installed / on PATH."
    Write-Host "  Install it first, then re-run this script:"
    Write-Host "    pip install TTS_ka            (add [hotkeys] for global hotkeys)"
    Write-Host "  Verify with:  TTS_ka --version   (or: python -m TTS_ka --version)"
    exit 1
}
Write-Host "[ok]  TTS_ka is runnable."

# --- Prerequisite: AutoHotkey v2 (hotkeys only) ---------------------------
$haveAhk = Test-AutoHotkeyV2
if (-not $SkipHotkeys) {
    if ($haveAhk) {
        Write-Host "[ok]  AutoHotkey v2 found."
    } else {
        Write-Warning "AutoHotkey v2 not found - hotkeys need it. Install with:"
        Write-Host "    winget install AutoHotkey.AutoHotkey"
        Write-Host "  (The right-click context menu works without AutoHotkey.)"
    }
}

# --- Install context menu -------------------------------------------------
if (-not $SkipContextMenu) {
    Write-Host ""
    Write-Host "-> Registering context menu..."
    $ctxArgs = @{ WhatIf = [bool]$WhatIf }
    if ($PythonPath) { $ctxArgs["PythonPath"] = $PythonPath }
    if ($Languages -and $Languages.Count -gt 0) { $ctxArgs["Languages"] = $Languages }
    & $ContextPs1 @ctxArgs
}

# --- Install hotkeys (only if AHK present) --------------------------------
if (-not $SkipHotkeys -and $haveAhk) {
    Write-Host ""
    Write-Host "-> Installing global hotkeys..."
    & $HotkeysPs1 -WhatIf:$WhatIf
}

# --- Summary --------------------------------------------------------------
Write-Host ""
Write-Host "What you can do now"
Write-Host ("-" * 40)
if (-not $SkipContextMenu) {
    Write-Host "  * Copy text (Ctrl+C), right-click empty space in Explorer/Desktop"
    Write-Host "    -> 'Read with TTS_ka' -> pick a language."
}
if (-not $SkipHotkeys -and $haveAhk) {
    Write-Host "  * Global hotkeys: Alt+E (English), Alt+R (Russian), Alt+X (Georgian)."
    Write-Host "    Apps key (or Ctrl+Alt+Right-click) opens a language menu anywhere."
}
Write-Host ""
Write-Host "  Note: Windows cannot add items to the text-selection menu inside Chrome,"
Write-Host "        Edge, or Word. Use the AutoHotkey Apps-key menu there instead."
Write-Host ""
Write-Host "  Verify your audio setup:  TTS_ka --doctor"
Write-Host "  Uninstall everything:     ...\Install-TTS_ka-Windows.ps1 -Uninstall"
