# __main__.py inside your TTS_ka package
import os
import sys
import time
import subprocess
import keyboard
import pyperclip
import win32com.client

# --- Auto Startup Shortcut Creation ---

def create_startup_shortcut():
    """
    Creates a shortcut in the Windows Startup folder so that TTS_ka 
    automatically launches in hotkey mode when the user logs in.
    """
    startup_folder = os.path.join(
        os.environ['APPDATA'], "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    )
    shortcut_path = os.path.join(startup_folder, "TTS_ka_Hotkeys.lnk")
    
    # Only create the shortcut if it doesn't already exist.
    if os.path.exists(shortcut_path):
        return

    # Get the full path to the Python executable and current module.
    python_exe = sys.executable
    # We want to launch TTS_ka in hotkey mode (i.e. with no extra arguments)
    # so that it sets up the global shortcuts.
    shortcut_args = "-m TTS_ka"

    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(shortcut_path)
    shortcut.TargetPath = python_exe
    shortcut.Arguments = shortcut_args
    shortcut.WorkingDirectory = os.path.dirname(os.path.abspath(__file__))
    shortcut.IconLocation = python_exe  # (optional)
    shortcut.save()
    print(f"Startup shortcut created at: {shortcut_path}")

# --- TTS Functionality (replace with your actual implementation) ---

def perform_tts(text, lang="ka"):
    """
    Replace this with your TTS code. This function is called both by the
    hotkey launcher and when text is passed via command line.
    """
    # For example, you might have your text-to-speech logic here:
    print(f"Performing TTS in {lang} for text: {text}")
    # If your module already implements TTS functionality, call it here.
    # e.g., from .tts import speak
    #       speak(text, lang)
    # For this example we simulate by printing.
    # Optionally, you can launch a subprocess if TTS_ka is intended to be run this way:
    # command = f'py -m TTS_ka "{text}" {lang}'
    # subprocess.Popen(command, shell=True)

# --- Hotkey Functions ---

def vocalize(lang="ka"):
    """
    Simulates a Ctrl+C to copy selected text, then calls perform_tts.
    """
    keyboard.press_and_release('ctrl+c')
    time.sleep(0.2)
    text = pyperclip.paste().replace('\r\n', '\n')
    if not text.strip():
        print("No text was copied from the clipboard.")
        return
    perform_tts(text, lang)

def run_hotkeys():
    """
    Registers global hotkeys for TTS:
      - Alt+X for default (Georgian, "ka")
      - Alt+R for Russian ("ru")
      - Alt+E for English ("eng")
    Also creates the startup shortcut so these hotkeys auto-run on login.
    """
    create_startup_shortcut()
    keyboard.add_hotkey('alt+x', lambda: vocalize("ka"))
    keyboard.add_hotkey('alt+r', lambda: vocalize("ru"))
    keyboard.add_hotkey('alt+e', lambda: vocalize("eng"))
    print("Hotkeys registered:")
    print("  Alt+X -> TTS (ka)")
    print("  Alt+R -> TTS (ru)")
    print("  Alt+E -> TTS (eng)")
    print("Press ESC to exit hotkey mode.")
    keyboard.wait('esc')

# --- Main Entry Point ---

def main():
    if len(sys.argv) == 1:
        # No extra arguments: launch hotkey mode
        run_hotkeys()
    else:
        # If arguments are provided, assume the first argument is text and the
        # optional second argument is the language.
        text = sys.argv[1]
        lang = sys.argv[2] if len(sys.argv) > 2 else "ka"
        perform_tts(text, lang)

if __name__ == '__main__':
    main()
