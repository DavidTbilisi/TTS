<#
    TTS_ka — copy hotkeys script into Windows Startup and launch AutoHotkey v2.

    Run from repository root (recommended):
        powershell -ExecutionPolicy Bypass -File .\extras\autohotkey\Install-TTS_ka-Hotkeys.ps1

    Or from this folder:
        cd $PSScriptRoot
        powershell -ExecutionPolicy Bypass -File .\Install-TTS_ka-Hotkeys.ps1

    Options:
        -WhatIf   Show paths only, do not copy or start.
        -NoStart  Copy to Startup but do not launch AutoHotkey now.
        -Uninstall Remove TTS_ka_hotkeys.ahk from Startup (does not uninstall AutoHotkey).
#>
param(
    [switch] $WhatIf,
    [switch] $NoStart,
    [switch] $Uninstall
)

$ErrorActionPreference = "Stop"
$ScriptName = "TTS_ka_hotkeys.ahk"
$SourceAhk = Join-Path $PSScriptRoot $ScriptName
if (-not (Test-Path -LiteralPath $SourceAhk)) {
    Write-Error "Missing $ScriptName next to this installer: $SourceAhk"
}

$Startup = [Environment]::GetFolderPath("Startup")
$DestAhk = Join-Path $Startup $ScriptName

function Find-AutoHotkeyV2 {
    $names = @("AutoHotkey64.exe", "AutoHotkey32.exe")
    $roots = @(
        "${env:ProgramFiles}\AutoHotkey\v2",
        "${env:ProgramFiles(x86)}\AutoHotkey\v2",
        "${env:LocalAppData}\Programs\AutoHotkey\v2"
    )
    foreach ($r in $roots) {
        foreach ($n in $names) {
            $p = Join-Path $r $n
            if (Test-Path -LiteralPath $p) { return $p }
        }
    }
    $cmd = Get-Command "AutoHotkey64.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

if ($Uninstall) {
    if (Test-Path -LiteralPath $DestAhk) {
        if ($WhatIf) { Write-Host "WhatIf: remove $DestAhk" }
        else {
            Remove-Item -LiteralPath $DestAhk -Force
            Write-Host "Removed: $DestAhk"
        }
    } else {
        Write-Host "Nothing to remove: $DestAhk"
    }
    exit 0
}

Write-Host "Source: $SourceAhk"
Write-Host "Startup: $DestAhk"

if ($WhatIf) {
    Write-Host "WhatIf: Copy-Item and optionally Start-Process skipped."
    exit 0
}

Copy-Item -LiteralPath $SourceAhk -Destination $DestAhk -Force
Write-Host "Installed to Startup folder."

$ahk = Find-AutoHotkeyV2
if (-not $ahk) {
    Write-Warning "AutoHotkey v2 not found. Install from https://www.autohotkey.com/ then run:"
    Write-Host "  `"$DestAhk`""
    exit 1
}

Write-Host "AutoHotkey: $ahk"

if (-not $NoStart) {
    Start-Process -FilePath $ahk -ArgumentList "`"$DestAhk`""
    Write-Host "Started hotkeys script."
} else {
    Write-Host "Skipped start (-NoStart). Log off/on or run the .ahk manually."
}

Write-Host ""
Write-Host "Next: edit flags in $DestAhk (or edit repo copy and re-run this installer)."
Write-Host "Python must work in a new cmd window:  python -m TTS_ka --version"
