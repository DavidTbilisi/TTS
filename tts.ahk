#Requires AutoHotkey v2.0
^!r::Reload  ; Ctrl+Alt+R

; Python path 
pathToPython := "C:\laragon\www\python\TTS\venv\Scripts\python.exe"
pathToMain := "C:\laragon\www\python\TTS\main.py"

Vocalize(lang:="ka"){
    Send "{CtrlDown}{c}{Ctrlup}"
    
    if lang == "ka" {
        Run pathToPython " " pathToMain " ka"
    } else if lang == "ru" {
        Run pathToPython " " pathToMain " ru"
    } else {
        Run pathToPython " " pathToMain " en"
    }
    return  
}


!x::Vocalize() ; default is Georgian
!r::Vocalize("ru") 
!e::Vocalize("eng") 

