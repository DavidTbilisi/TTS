"""Simple ASCII-only help system for Windows compatibility."""


def show_simple_help():
    """Show simple help without Unicode characters."""
    print("")
    print("=" * 70)
    print("           ULTRA-FAST TTS - Maximum Speed Generation")
    print("=" * 70)
    print("")

    print("SUPPORTED LANGUAGES:")
    print("  ka  - Georgian  (Premium quality)")
    print("  ru  - Russian   (Fast neural voice)")
    print("  en  - English   (Maximum speed)")
    print("")

    print("QUICK START EXAMPLES:")
    print('  python -m TTS_ka "Hello world" --turbo --lang en')
    print('  python -m TTS_ka "Привет мир" --turbo --lang ru')
    print("  python -m TTS_ka clipboard --turbo --lang ka")
    print("  python -m TTS_ka file.txt --turbo --lang en")
    print("")

    print("PERFORMANCE MODES:")
    print("  --turbo                Maximum speed (RECOMMENDED)")
    print("  --chunk-seconds 30     Custom chunk size")
    print("  --parallel 6           Multiple workers")
    print("")

    print("SPEED COMPARISON (1000 words):")
    print("  Direct generation:     15-25 seconds")
    print("  Turbo mode:           8-15 seconds")
    print("  Chunked parallel:     6-12 seconds")
    print("")

    print("COMMON WORKFLOWS:")
    print("  1. Copy text -> python -m TTS_ka clipboard --turbo")
    print("  2. File input -> python -m TTS_ka file.txt --turbo --lang ru")
    print("  3. Batch mode -> Add --no-play flag")
    print("")

    print("OPTIMIZATION TIPS:")
    print("  * Always use --turbo for best performance")
    print("  * Georgian: Highest quality, slightly slower")
    print("  * Russian/English: Maximum speed")
    print("  * Use clipboard workflow for fastest operation")
    print("")


def show_troubleshooting():
    """Show troubleshooting guide."""
    print("TROUBLESHOOTING:")
    print("=" * 50)
    print("")

    print("Slow generation:")
    print("  -> Use --turbo flag")
    print("  -> Increase --parallel workers (4-8)")
    print("  -> Check internet speed")
    print("")

    print("Language errors:")
    print("  -> Use only: ka, ru, en")
    print("  -> Check text encoding (UTF-8)")
    print("  -> Try simple ASCII text first")
    print("")

    print("File not found:")
    print("  -> Use full file paths")
    print("  -> Try 'clipboard' instead")
    print("  -> Check file permissions")
    print("")

    print("No audio playback:")
    print("  -> Check data.mp3 is created")
    print("  -> Use --no-play and open manually")
    print("  -> Verify system audio support")
    print("")


def show_comprehensive_help():
    """Expose a comprehensive help function used by some tests (wraps simple help + troubleshooting)."""
    show_simple_help()
    show_troubleshooting()


if __name__ == "__main__":
    show_simple_help()
    show_troubleshooting()
