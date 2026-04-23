<#
.SYNOPSIS
  Optional Windows shell: read the clipboard with TTS_ka from the context menu.

.DESCRIPTION
  Registers per-user (HKCU) verbs on:
    - File Explorer empty area (Directory\Background\shell)
    - Desktop empty area (DesktopBackground\shell)

  Default: one cascading menu "Read with TTS_ka" -> English / Russian / Georgian / Georgian (male).

  Optional: right-click on .txt files to read the file path (-IncludeTextFiles).

  Typical workflow (Explorer/Desktop): copy text (Ctrl+C), right-click empty space,
  open "Read with TTS_ka", pick a language.

  NOTE: Windows cannot add items to the text-selection menu inside Chrome, Edge, Word,
  etc. via registry. For that, use extras/autohotkey/TTS_ka_hotkeys.ahk (Apps key or
  Ctrl+Alt+Right-click language menu).

.PARAMETER Languages
  Codes for TTS_ka --lang. Default: all of en, ru, ka, ka-m when using nested menu;
  when -FlatMenu, default is en only unless you pass -Languages explicitly.

.PARAMETER FlatMenu
  Register one top-level item per language (old style) instead of a single submenu.

.PARAMETER PythonPath
  Path to python.exe, or "python" / "py" if on PATH.

.PARAMETER ExtraArgs
  Extra CLI flags, e.g. "--stream".

.PARAMETER IncludeTextFiles
  Add per-language entries on .txt right-click (uses "%1" file path).

.PARAMETER Uninstall
  Remove all TTS_ka.* context-menu keys created by this script.

.PARAMETER WhatIf
  Print actions only; do not modify the registry.
#>
param(
    [string[]] $Languages = @(),
    [switch] $FlatMenu,
    [string] $PythonPath = "",
    [string] $ExtraArgs = "",
    [switch] $IncludeTextFiles,
    [switch] $Uninstall,
    [switch] $WhatIf
)

$ErrorActionPreference = "Stop"

$RootBg = "Registry::HKEY_CURRENT_USER\Software\Classes\Directory\Background\shell"
$DeskBg = "Registry::HKEY_CURRENT_USER\Software\Classes\DesktopBackground\Shell"
$TxtShell = "Registry::HKEY_CURRENT_USER\Software\Classes\txtfile\shell"

$VerbPrefix = "TTS_ka."
$VerbClipboard = "$VerbPrefix" + "clipboard."
$VerbFile = "$VerbPrefix" + "readfile."
$NestedParentName = "TTS_ka.ReadClipboard"

function Resolve-Languages {
    param([string[]] $Langs, [bool] $Flat)
    if ($Langs -and $Langs.Count -gt 0) { return $Langs }
    if ($Flat) { return @("en") }
    return @("en", "ru", "ka", "ka-m")
}

function Resolve-Python {
    param([string] $Explicit)
    if ($Explicit) { return $Explicit }
    foreach ($name in @("python", "py")) {
        $c = Get-Command $name -ErrorAction SilentlyContinue
        if ($c) { return $c.Source }
    }
    return "python"
}

function Escape-ForCmdK {
    param([string] $PythonExe)
    if ($PythonExe -match '[\s"]') {
        return '"' + ($PythonExe -replace '"', '\"') + '"'
    }
    return $PythonExe
}

function Build-CommandLine {
    param(
        [string] $PythonExe,
        [string] $Lang,
        [string] $Extra,
        [switch] $UseFilePlaceholder
    )
    $py = Escape-ForCmdK $PythonExe
    $tail = if ($UseFilePlaceholder) {
        '"%1" --lang ' + $Lang
    } else {
        'clipboard --lang ' + $Lang
    }
    if ($Extra) { $tail += " " + $Extra.Trim() }
    return "cmd.exe /k $py -m TTS_ka $tail"
}

function Lang-Label {
    param([string] $Lang)
    switch ($Lang) {
        "en" { "English" }
        "ru" { "Russian" }
        "ka" { "Georgian (female)" }
        "ka-m" { "Georgian (male)" }
        default { $Lang }
    }
}

function Remove-TtsKaKeys {
    param([string] $BasePath)
    if (-not (Test-Path -LiteralPath $BasePath)) { return }
    Get-ChildItem -LiteralPath $BasePath -ErrorAction SilentlyContinue |
        Where-Object { $_.PSChildName -like "$VerbPrefix*" } |
        ForEach-Object {
            $p = $_.PSPath
            if ($WhatIf) { Write-Host "WhatIf: remove $p" }
            else {
                Remove-Item -LiteralPath $p -Recurse -Force
                Write-Host "Removed: $p"
            }
        }
}

function Set-Verbs {
    param(
        [string] $VerbPath,
        [string] $Label,
        [string] $CommandLine
    )
    if ($WhatIf) {
        Write-Host "WhatIf: $VerbPath  (default) = $Label"
        Write-Host "WhatIf: $VerbPath\command  (default) = $CommandLine"
        return
    }
    New-Item -Path $VerbPath -Force | Out-Null
    New-ItemProperty -Path $VerbPath -Name "(default)" -Value $Label -PropertyType String -Force | Out-Null
    $cmdPath = Join-Path $VerbPath "command"
    New-Item -Path $cmdPath -Force | Out-Null
    New-ItemProperty -Path $cmdPath -Name "(default)" -Value $CommandLine -PropertyType String -Force | Out-Null
}

function Register-NestedClipboardMenu {
    param(
        [string] $ShellRoot,
        [string] $PythonExe,
        [string[]] $Langs,
        [string] $Extra
    )
    $parent = Join-Path $ShellRoot $NestedParentName
    $title = "Read with TTS_ka"
    if ($WhatIf) {
        Write-Host "WhatIf: nested parent $parent"
        foreach ($lang in $Langs) {
            $slug = ($lang -replace '[^a-zA-Z0-9]', '')
            $child = Join-Path (Join-Path $parent "Shell") ("lang_" + $slug)
            $lab = Lang-Label $lang
            $cmd = Build-CommandLine -PythonExe $PythonExe -Lang $lang -Extra $Extra
            Write-Host "WhatIf: $child  (default) = $lab"
            Write-Host "WhatIf: $child\command => $cmd"
        }
        return
    }
    New-Item -Path $parent -Force | Out-Null
    New-ItemProperty -Path $parent -Name "(default)" -Value $title -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $parent -Name "MUIVerb" -Value $title -PropertyType String -Force | Out-Null

    foreach ($lang in $Langs) {
        $slug = ($lang -replace '[^a-zA-Z0-9]', '')
        $child = Join-Path (Join-Path $parent "Shell") ("lang_" + $slug)
        $lab = Lang-Label $lang
        $cmd = Build-CommandLine -PythonExe $PythonExe -Lang $lang -Extra $Extra
        Set-Verbs -VerbPath $child -Label $lab -CommandLine $cmd
    }
    Write-Host "Registered nested: $title under $ShellRoot"
}

function Register-FlatClipboardMenus {
    param(
        [string] $ShellRoot,
        [string] $PythonExe,
        [string[]] $Langs,
        [string] $Extra
    )
    foreach ($lang in $Langs) {
        $keySuffix = ($lang -replace '[^a-zA-Z0-9]', '')
        $verbName = "$VerbClipboard$keySuffix"
        $label = "TTS_ka: Read clipboard - $(Lang-Label $lang)"
        $cmd = Build-CommandLine -PythonExe $PythonExe -Lang $lang -Extra $Extra
        $verbPath = Join-Path $ShellRoot $verbName
        Set-Verbs -VerbPath $verbPath -Label $label -CommandLine $cmd
        Write-Host "Registered: $label"
    }
}

if ($Uninstall) {
    Remove-TtsKaKeys $RootBg
    Remove-TtsKaKeys $DeskBg
    Remove-TtsKaKeys $TxtShell
    exit 0
}

$langResolved = Resolve-Languages $Languages $FlatMenu
$pyExe = Resolve-Python $PythonPath
Write-Host "Python: $pyExe"
Write-Host "Languages: $($langResolved -join ', ')"
Write-Host "Layout: $(if ($FlatMenu) { 'flat' } else { 'nested submenu' })"

foreach ($base in @($RootBg, $DeskBg)) {
    if ($FlatMenu) {
        Register-FlatClipboardMenus -ShellRoot $base -PythonExe $pyExe -Langs $langResolved -Extra $ExtraArgs
    } else {
        Register-NestedClipboardMenu -ShellRoot $base -PythonExe $pyExe -Langs $langResolved -Extra $ExtraArgs
    }
}

if ($IncludeTextFiles) {
    foreach ($lang in $langResolved) {
        $keySuffix = ($lang -replace '[^a-zA-Z0-9]', '')
        $verbNameL = "${VerbFile}txt_$keySuffix"
        $labelL = "TTS_ka: Read this file - $(Lang-Label $lang)"
        $cmd = Build-CommandLine -PythonExe $pyExe -Lang $lang -Extra $ExtraArgs -UseFilePlaceholder
        $verbPath = Join-Path $TxtShell $verbNameL
        Set-Verbs -VerbPath $verbPath -Label $labelL -CommandLine $cmd
        Write-Host "Registered (txt): $labelL"
    }
}

Write-Host ""
Write-Host "Explorer / Desktop: copy text, right-click empty area -> Read with TTS_ka -> language."
Write-Host "In Chrome/Word selection menu: not supported by Windows; use AutoHotkey (Apps key or Ctrl+Alt+right-click) in TTS_ka_hotkeys.ahk."
Write-Host "Windows 11: you may need 'Show more options' for classic shell entries."
Write-Host "Remove: powershell ...\Install-TTS_ka-ContextMenu.ps1 -Uninstall"
