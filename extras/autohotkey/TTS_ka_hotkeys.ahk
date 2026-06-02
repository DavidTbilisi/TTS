#Requires AutoHotkey v2.0
#SingleInstance Force

; =============================================================================
; TTS_ka — Windows hotkeys (AutoHotkey v2)
; =============================================================================
; Install once (from repo):  powershell -ExecutionPolicy Bypass -File extras\autohotkey\Install-TTS_ka-Hotkeys.ps1
; Or: copy this file to your Startup folder and double-click it after installing AutoHotkey v2.
;
; Default workflow: select or copy text, then press a hotkey (see ACTIVE HOTKEYS below).
; Most extras are commented — remove the leading semicolon (;) on lines you want.
; =============================================================================

; -----------------------------------------------------------------------------
; CONFIG — edit these first if something fails
; -----------------------------------------------------------------------------
global g_Python := "python"    ; try "py", "py -3", or full path e.g. A_ProgramFiles "\Python312\python.exe"
global g_CmdKeepOpen := false  ; false = cmd /c (window closes when done); true = cmd /k (stays open for debugging)
global g_CopyFirst := true     ; true = send Ctrl+C first — highlight text and press hotkey; false = clipboard must already contain text

; Extra CLI flags appended to every run (empty = defaults). Examples (pick one style, uncomment in your copy):
; global g_ExtraFlags := "--stream"
; global g_ExtraFlags := "--stream --no-gui"
; global g_ExtraFlags := "--chunk-seconds 30 --parallel 6"
; global g_ExtraFlags := "-o " . A_MyDocuments "\last_tts.mp3"
global g_ExtraFlags := ""

; Working directory for the shell (often fine blank = script dir)
global g_WorkingDir := A_ScriptDir

; PID of the most recently launched synthesis process (used by the stop hotkey)
global g_LastPID := 0

; -----------------------------------------------------------------------------
; Tray menu (right-click green H in notification area)
; -----------------------------------------------------------------------------
A_IconTip := "TTS_ka hotkeys  ·  Alt+E/R/X  ·  Ctrl+Shift+E/R/X (stream)  ·  Alt+Q stop"
A_TrayMenu.Add("Reload this script", (*) => Reload())
A_TrayMenu.Add()
A_TrayMenu.Add("Exit", (*) => ExitApp())
TrayTip("TTS_ka", "Ready  ·  Alt+E R X  ·  Ctrl+Shift+E R X (stream)  ·  Alt+Q stop", 4)

; -----------------------------------------------------------------------------
; Core — you rarely need to change below here
; -----------------------------------------------------------------------------
; Run synthesis using whatever is already on the clipboard (no Ctrl+C here).
; Accepts an optional extraFlags override (e.g. "--stream") that takes precedence over g_ExtraFlags.
RunTTS_Impl(lang, extraOverride := "") {
    global g_Python, g_CmdKeepOpen, g_ExtraFlags, g_WorkingDir, g_LastPID
    slash := g_CmdKeepOpen ? "/k" : "/c"
    rest := " -m TTS_ka clipboard --lang " . lang
    flags := (extraOverride != "") ? extraOverride : g_ExtraFlags
    if StrLen(Trim(flags))
        rest .= " " . flags
    py := g_Python
    if InStr(py, " ")
        py := '"' . py . '"'
    cmdline := py . rest
    Run(A_ComSpec " " . slash . " " . cmdline, g_WorkingDir, , &pid)
    g_LastPID := pid
}

RunTTS(lang) {
    global g_CopyFirst
    if g_CopyFirst {
        Send("^c")
        if !ClipWait(0.8) {
            TrayTip("TTS_ka", "Nothing on clipboard — select text first.", 3)
            return
        }
        Sleep(50)
    }
    RunTTS_Impl(lang)
}

; Same as RunTTS but forces --stream (needs VLC / mpv installed).
RunTTS_Stream(lang) {
    global g_CopyFirst
    if g_CopyFirst {
        Send("^c")
        if !ClipWait(0.8) {
            TrayTip("TTS_ka", "Nothing on clipboard — select text first.", 3)
            return
        }
        Sleep(50)
    }
    RunTTS_Impl(lang, "--stream")
}

; Select text in any app, then: Apps (menu) key OR Ctrl+Alt+right-click -> pick language.
; (Windows cannot add "Read -> language" into Chrome/Word's own right-click menu via registry.)
ShowReadLanguageMenu(*) {
    Send("^c")
    if !ClipWait(0.8) {
        TrayTip("TTS_ka", "No copy: select text first, then open this menu.", 3)
        return
    }
    Sleep(50)
    m := Menu()
    m.Add("English", (*) => RunTTS_Impl("en"))
    m.Add("Russian", (*) => RunTTS_Impl("ru"))
    m.Add("Georgian (female)", (*) => RunTTS_Impl("ka"))
    m.Add("Georgian (male)", (*) => RunTTS_Impl("ka-m"))
    m.Add()
    m.Add("Cancel", (*) => {})
    MouseGetPos &mx, &my
    m.Show(mx, my)
}

; =============================================================================
; IN-APP: select text -> language menu (closest to "right-click Read -> language")
; =============================================================================
AppsKey:: ShowReadLanguageMenu()     ; Menu key (next to Right Ctrl): copy selection, then pick language
^!RButton:: ShowReadLanguageMenu()   ; Ctrl+Alt+right-click at cursor: same (blocks normal context menu)

; =============================================================================
; ACTIVE HOTKEYS
; =============================================================================
!e:: RunTTS("en")      ; Alt+E         — English
!r:: RunTTS("ru")      ; Alt+R         — Russian
!x:: RunTTS("ka")      ; Alt+X         — Georgian (female)
!+x:: RunTTS("ka-m")   ; Alt+Shift+X   — Georgian (male)

; Streaming variants — plays each chunk as it synthesizes (needs mpv/VLC/ffplay)
; Audio starts within ~1 s of pressing the hotkey.  The cmd window closes once
; generation is done; that is normal — mpv continues playing in the background.
!+e:: RunTTS_Stream("en")   ; Alt+Shift+E — English, streaming
!+r:: RunTTS_Stream("ru")   ; Alt+Shift+R — Russian, streaming

; Ctrl+Shift variants — same actions, alternative modifier (some find it easier)
^+e:: RunTTS_Stream("en")   ; Ctrl+Shift+E — English, streaming
^+r:: RunTTS_Stream("ru")   ; Ctrl+Shift+R — Russian, streaming
^+x:: RunTTS_Stream("ka")   ; Ctrl+Shift+X — Georgian (female), streaming

; =============================================================================
; STOP / KILL — abort the current synthesis
; =============================================================================
!q:: {                           ; Alt+Q — kill the running TTS and its child python
    global g_LastPID
    if g_LastPID {
        try Run("taskkill /F /T /PID " . g_LastPID,, "Hide")
        g_LastPID := 0
    }
    TrayTip("TTS_ka", "Stopped.", 2)
}


; =============================================================================
; DUPLICATE BINDINGS WITH MODIFIERS (examples — uncomment one block at a time)
; =============================================================================
; ^!e:: RunTTS("en")     ; Ctrl+Alt+E — English (alternative)
; ^!r:: RunTTS("ru")
; ^!k:: RunTTS("ka")


; =============================================================================
; HEADLESS STREAMING (VLC dummy UI) — append flags (uncomment hotkeys)
; =============================================================================
; F9:: {
;     global g_Python, g_CmdKeepOpen, g_CopyFirst, g_WorkingDir
;     if g_CopyFirst {
;         Send("^c")
;         if !ClipWait(0.8)
;             return
;         Sleep(50)
;     }
;     slash := g_CmdKeepOpen ? "/k" : "/c"
;     py := g_Python
;     if InStr(py, " ")
;         py := '"' . py . '"'
;     Run(A_ComSpec " " . slash . " " . py . " -m TTS_ka clipboard --lang en --stream --no-gui", g_WorkingDir)
; }


; =============================================================================
; READ FROM FILE — set path, uncomment hotkey
; =============================================================================
; global g_LastFile := A_MyDocuments "\article.txt"
; F8:: {
;     global g_Python, g_CmdKeepOpen, g_LastFile, g_WorkingDir
;     slash := g_CmdKeepOpen ? "/k" : "/c"
;     py := g_Python
;     if InStr(py, " ")
;         py := '"' . py . '"'
;     Run(A_ComSpec " " . slash . " " . py . " -m TTS_ka """ . g_LastFile . """ --lang en", g_WorkingDir)
; }


; =============================================================================
; NO TERMINAL WINDOW — Run python directly (harder to see errors)
; =============================================================================
; RunTTS_Hidden(lang) {
;     global g_Python, g_CopyFirst, g_WorkingDir
;     if g_CopyFirst {
;         Send("^c")
;         if !ClipWait(0.8)
;             return
;         Sleep(50)
;     }
;     py := g_Python
;     if InStr(py, " ")
;         py := '"' . py . '"'
;     Run(py . " -m TTS_ka clipboard --lang " . lang, g_WorkingDir, "Hide")
; }
; ^#e:: RunTTS_Hidden("en")


; =============================================================================
; RELOAD SCRIPT — Ctrl+Win+R (comment out if it clashes)
; =============================================================================
^#r:: Reload()


; =============================================================================
; CONTEXT-SENSITIVE (only when certain window active) — template
; =============================================================================
; #HotIf WinActive("ahk_exe chrome.exe")
; !e:: RunTTS("en")
; #HotIf


; =============================================================================
; LEGACY v1-style (Alt & key) — same as !e if you prefer explicit ampersand
; =============================================================================
; Alt & y:: RunTTS("en")
