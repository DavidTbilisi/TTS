#Requires AutoHotkey v2.0


readClipboardAndSpeak(lang) {
    Send("^c")
    if (ClipWait(1)) { ; Wait up to 1 second for the clipboard to contain data
        Sleep(50)
        TrayTip()
    ; Run the TTS CLI inside cmd /k so the terminal stays open after completion
    cmd := "cmd /k py -m TTS_ka --lang " . lang . " clipboard --chunk-seconds 45 --parallel 3 --no-play"
    Run(cmd)
    } else {
        TrayTip("Clipboard", "Failed to copy text to clipboard")
        Sleep(1000)
        TrayTip()
    }
}


; AutoHotkey v2
AutoClickEnabled := false
AutoClickInterval := 500  ; ms

!l:: {
    global AutoClickEnabled, AutoClickInterval

    if (!AutoClickEnabled) {
        res := InputBox("Enter click interval (ms):", "Click Speed",, AutoClickInterval)
        if (res.Result = "Cancel")
            return
        try {
            AutoClickInterval := Max(10, Floor(res.Value + 0))  ; clamp to ≥10ms
        } catch {
            AutoClickInterval := 500
        }
        SetTimer AutoClickTimer, AutoClickInterval  ; start
        AutoClickEnabled := true
        TrayTip "AutoClicker", "Started at " AutoClickInterval " ms"
    } else {
        SetTimer AutoClickTimer, 0  ; stop
        AutoClickEnabled := false
        TrayTip "AutoClicker", "Stopped"
    }
}

AutoClickTimer() {
    Click()  ; v2 function form
}


; Press Alt + M to toggle holding the left mouse button on/off
!m:: {
    global Toggle
    Toggle := !Toggle
    if (Toggle) {
        Send("{LButton down}")  ; Hold down the left mouse button
    } else {
        Send("{LButton up}")  ; Release the left mouse button
    }
}







Alt & e::readClipboardAndSpeak("en")
Alt & r::readClipboardAndSpeak("ru")
Alt & x::readClipboardAndSpeak("ka")

; If you want to read a file, put its path in a variable and run the CLI directly, for example:
; filePath := "D:\\Code\\python\\TTS\\tests\\test_reading.txt"
; Run("py -m TTS_ka " . filePath . " --lang en --chunk-seconds 45 --parallel 3 --no-play")


; Calendar and To Do shortcuts
#HotIf GetKeyState("Ctrl") ; Enable hotkeys only when Ctrl is pressed
n & m::{
   
    Run("http://localhost:9002/projects/great-britain/gantt?query_id=32")
    Run("https://calendar.google.com/calendar/u/0/r/customday")
    ; local Microsoft To Do application
    Run("C:\Program Files\WindowsApps\Microsoft.Todos_2.148.3611.0_x64__8wekyb3d8bbwe\Todo.exe")
}


; Money shortcuts
#HotIf GetKeyState("Ctrl") 
m & y:: {
    Run("http://localhost:8000/")
    Run("https://tbconline.ge/tbcrd/login")
    Run("https://docs.google.com/spreadsheets/d/1a77c-meq-6jgx2xoIxpZhyM-xDZ3XYELZvlEgSNQZvg/edit?gid=2016596698#gid=2016596698")
}


; Reload shortcut
#HotIf GetKeyState("Ctrl") 
r & e::Reload ; Reload the script keys: Ctrl + R
