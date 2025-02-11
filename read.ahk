#Requires AutoHotkey v2.0


readClipboardAndSpeak(lang) {
    Send("^c")
    if (ClipWait(1)) { ; Wait up to 1 second for the clipboard to contain data
        Sleep(1000)
        TrayTip()
        Run("py -m TTS_ka --lang " . lang . " clipboard")
    } else {
        TrayTip("Clipboard", "Failed to copy text to clipboard")
        Sleep(1000)
        TrayTip()
    }
}

Alt & e::readClipboardAndSpeak("en")
Alt & r::readClipboardAndSpeak("ru")
Alt & x::readClipboardAndSpeak("ka")