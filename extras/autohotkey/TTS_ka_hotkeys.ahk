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
global g_Python := "python"   ; try "py", "py -3", or full path e.g. A_ProgramFiles "\Python312\python.exe"
global g_CmdKeepOpen := true  ; true = cmd /k (see errors); false = cmd /c (closes when done)
global g_CopyFirst := false   ; true = send Ctrl+C before TTS (use when you highlight text instead of copying)

; Extra CLI flags appended to every run (empty = defaults). Examples (pick one style, uncomment in your copy):
; global g_ExtraFlags := "--stream"
; global g_ExtraFlags := "--stream --no-gui"
; global g_ExtraFlags := "--chunk-seconds 30 --parallel 6"
; global g_ExtraFlags := "-o " . A_MyDocuments "\last_tts.mp3"
global g_ExtraFlags := ""

; Working directory for the shell (often fine blank = script dir)
global g_WorkingDir := A_ScriptDir

; -----------------------------------------------------------------------------
; Tray menu (right-click green H in notification area)
; -----------------------------------------------------------------------------
A_IconTip := "TTS_ka hotkeys"
A_TrayMenu.Add("Reload this script", (*) => Reload())
A_TrayMenu.Add()
A_TrayMenu.Add("Exit", (*) => ExitApp())

; -----------------------------------------------------------------------------
; Core — you rarely need to change below here
; -----------------------------------------------------------------------------
; Run synthesis using whatever is already on the clipboard (no Ctrl+C here).
RunTTS_Impl(lang) {
    global g_Python, g_CmdKeepOpen, g_ExtraFlags, g_WorkingDir
    slash := g_CmdKeepOpen ? "/k" : "/c"
    rest := " -m TTS_ka clipboard --lang " . lang
    if StrLen(Trim(g_ExtraFlags))
        rest .= " " . g_ExtraFlags
    py := g_Python
    if InStr(py, " ")
        py := '"' . py . '"'
    cmdline := py . rest
    Run(A_ComSpec " " . slash . " " . cmdline, g_WorkingDir)
}

RunTTS(lang) {
    global g_CopyFirst
    if g_CopyFirst {
        Send("^c")
        if !ClipWait(0.8) {
            TrayTip("TTS_ka", "Nothing appeared on the clipboard after Ctrl+C.", 3)
            return
        }
        Sleep(50)
    }
    RunTTS_Impl(lang)
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
; ACTIVE HOTKEYS (defaults: Alt + letter — same idea as the readme)
; =============================================================================
!e:: RunTTS("en")     ; Alt+E — English
!r:: RunTTS("ru")     ; Alt+R — Russian
!x:: RunTTS("ka")     ; Alt+X — Georgian (female)

; =============================================================================
; MORE LANGUAGES — uncomment to enable
; =============================================================================
; !+x:: RunTTS("ka-m")   ; Alt+Shift+X — Georgian male


; =============================================================================
; DUPLICATE BINDINGS WITH MODIFIERS (examples — uncomment one block at a time)
; =============================================================================
; ^!e:: RunTTS("en")     ; Ctrl+Alt+E — English (alternative)
; ^!r:: RunTTS("ru")
; ^!k:: RunTTS("ka")


; =============================================================================
; STREAMING VARIANTS — same keys but with streaming (set g_ExtraFlags instead
; for global streaming, or duplicate RunTTS calls with inline flags below)
; =============================================================================
; !e:: RunTTS("en")   ; if you use this, comment the default !e above first
; Actually use g_ExtraFlags := "--stream" at top, or define a second function:

; RunTTS_Stream(lang) {
;     global g_Python, g_CmdKeepOpen, g_CopyFirst, g_WorkingDir
;     if g_CopyFirst {
;         Send("^c")
;         if !ClipWait(0.8) {
;             TrayTip("TTS_ka", "Clipboard empty.", 3)
;             return
;         }
;         Sleep(50)
;     }
;     slash := g_CmdKeepOpen ? "/k" : "/c"
;     py := g_Python
;     if InStr(py, " ")
;         py := '"' . py . '"'
;     Run(A_ComSpec " " . slash . " " . py . " -m TTS_ka clipboard --lang " . lang . " --stream", g_WorkingDir)
; }
; !+e:: RunTTS_Stream("en")
; !+r:: RunTTS_Stream("ru")
; !+s:: RunTTS_Stream("ka")


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
