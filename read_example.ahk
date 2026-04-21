#Requires AutoHotkey v2.0


readClipboardAndSpeak(lang) {
    Send("^c")
    if (ClipWait(1)) { ; Wait up to 1 second for the clipboard to contain data
        Sleep(50)
        TrayTip()
    ; Run the TTS CLI inside cmd /k so the terminal stays open after completion
    cmd := "cmd /k py -m TTS_ka --lang " . lang . " clipboard --chunk-seconds 45 --parallel 6 --no-cache"
    Run(cmd)
    } else {
        TrayTip("Clipboard", "Failed to copy text to clipboard")
        Sleep(1000)
        TrayTip()
    }
}


Alt & e::readClipboardAndSpeak("en")
Alt & r::readClipboardAndSpeak("ru")
Alt & x::readClipboardAndSpeak("ka")

; If you want to read a file, put its path in a variable and run the CLI directly, for example:
; filePath := "D:\\Code\\python\\TTS\\tests\\test_reading.txt"
; Run("py -m TTS_ka " . filePath . " --lang en --chunk-seconds 45 --parallel 3 --no-play")


; Reload shortcut
#HotIf GetKeyState("Ctrl") 
r & e::Reload ; Reload the script keys: Ctrl + R
