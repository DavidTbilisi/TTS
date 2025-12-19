"""Example: Using TTS_ka from Python.

This example shows how to use the public API for text-to-speech generation.
Safe to run — if dependencies are missing, the script prints what would run.

Usage:
    python examples/example_api.py
"""
import asyncio
import sys
from pathlib import Path

try:
    from TTS_ka import generate_audio, play_audio, sanitize_text
except Exception:
    print("TTS_ka package not importable. Activate your venv or install the package.")
    sys.exit(1)

OUT = Path("example_out.mp3")
TEXT = "Hello from TTS_ka! This is a short example using the async API."


async def main():
    """Run TTS examples."""
    # Sanitize text (best practice)
    clean_text = sanitize_text(TEXT)
    print(f"Sanitized text: {clean_text[:50]}...")

    # Example: generate_audio() -> creates an MP3 file
    print("\nExample: generate_audio() -> writes an MP3 file")
    try:
        success = await generate_audio(clean_text, "en", str(OUT))
        if success:
            print(f"✓ Generated: {OUT}")
            # Optionally play the audio
            print("Playing audio...")
            play_audio(str(OUT))
        else:
            print("✗ Generation failed (check dependencies/network)")
    except Exception as e:
        print(f"✗ Error: {e}")

    print("\nDone! Check example_out.mp3 in your file manager.")


if __name__ == "__main__":
    asyncio.run(main())

