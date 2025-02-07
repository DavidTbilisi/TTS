#Requires AutoHotkey v2.0
^!r::Reload  ; Ctrl+Alt+R

; Python path 
; pathToPython := "C:\laragon\www\python\TTS\venv\Scripts\python.exe"
; pathToMain := "C:\laragon\www\python\TTS\main.py"

Vocalize(lang:="ka"){
    global
    Send "{CtrlDown}{c}{Ctrlup}"
    ClipWait
    text := Clipboard
    text := StrReplace(text, "`r`n", "`n")

    if lang == "ka" {
        Run "py -m  TTS_ka " text " ka"
    } else if lang == "ru" {
        Run "py -m  TTS_ka " text " ru"
    } else {
        Run "py -m  TTS_ka " text " en"
    }
}


!x::Vocalize() ; default is Georgian
!r::Vocalize("ru") 
!e::Vocalize("eng") 

