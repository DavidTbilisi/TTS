"""Quick environment checker for runtime dependencies used by TTS_ka."""
import shutil
import sys

print("Checking environment for TTS_ka runtime dependencies...")

# Check ffmpeg
ffmpeg = shutil.which("ffmpeg")
if ffmpeg:
    print(f"ffmpeg: found at {ffmpeg}")
else:
    print("ffmpeg: NOT FOUND (install ffmpeg and add to PATH)")

# Check edge-tts
try:
    import edge_tts  # type: ignore
    print("edge-tts: installed")
except Exception:
    print("edge-tts: NOT INSTALLED (pip install edge-tts)")

# Check pydub
try:
    import pydub  # type: ignore
    print("pydub: installed")
except Exception:
    print("pydub: NOT INSTALLED (pip install pydub)")

print("Done.")

