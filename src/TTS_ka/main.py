"""Ultra-Fast Text-to-Speech CLI tool - No caching, direct generation."""

import argparse
import asyncio
import os
import time
import pyperclip

from .fast_audio import fast_generate_audio, play_audio, cleanup_http
from .ultra_fast import smart_generate_long_text, get_optimal_settings, OPTIMAL_WORKERS
from .chunking import should_chunk_text
from .simple_help import show_simple_help, show_troubleshooting





def get_input_text(text_input: str) -> str:
    """Process text input - handle clipboard, file paths, or direct text."""
    if text_input == "clipboard":
        text = pyperclip.paste().replace('\r\n', '\n')
        if not text.strip():
            print("No text was copied from the clipboard.")
            return ""
        return text
    
    # Check if it's a file path
    if os.path.exists(text_input) and os.path.isfile(text_input):
        with open(text_input, 'r', encoding='utf-8') as f:
            return f.read()
    
    return text_input


def main():
    parser = argparse.ArgumentParser(
        description='🚀 Ultra-Fast TTS - Georgian, Russian, English generation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  %(prog)s "Hello world" --turbo --lang en          # Quick English generation
  %(prog)s "გამარჯობა" --turbo --lang ka            # Georgian with maximum speed  
  %(prog)s file.txt --turbo --lang ru               # Russian from file
  %(prog)s clipboard --turbo                        # From clipboard (fastest workflow)

LANGUAGES: 🇬🇪 ka (Georgian) | 🇷🇺 ru (Russian) | 🇬🇧 en (English)
For comprehensive help with examples: %(prog)s --help-full
        """)
    
    parser.add_argument('text', nargs='?', help='Text to convert (file path, "clipboard", or direct text)')
    parser.add_argument('--lang', default='en', choices=['ka', 'ru', 'en'], 
                       help='Language: ka=Georgian(🇬🇪), ru=Russian(🇷🇺), en=English(🇬🇧)')
    parser.add_argument('--chunk-seconds', type=int, default=0, 
                       help='Chunk size in seconds (0=auto-detect, 20-60 recommended)')
    parser.add_argument('--parallel', type=int, default=0, 
                       help=f'Parallel workers (0=auto, 2-8 recommended, max={OPTIMAL_WORKERS})')
    parser.add_argument('--no-play', action='store_true', help='Skip automatic audio playback')
    parser.add_argument('--turbo', action='store_true', 
                       help='🚀 MAXIMUM SPEED mode (auto-optimizes everything - RECOMMENDED)')
    parser.add_argument('--help-full', action='store_true', 
                       help='Show comprehensive help with examples and workflows')
    
    args = parser.parse_args()
    
    # Handle comprehensive help
    if args.help_full:
        show_simple_help()
        show_troubleshooting()
        return
    
    # Get input text
    if not args.text:
        show_simple_help()
        print("ERROR: No text provided")
        print("Try: python -m TTS_ka 'your text' --turbo --lang en")
        return
    
    text = get_input_text(args.text)
    if not text:
        return
    output_path = 'data.mp3'
    
    # Auto-optimize settings in turbo mode
    if args.turbo:
        optimal = get_optimal_settings(text)
        if args.chunk_seconds == 0:
            args.chunk_seconds = optimal['chunk_seconds']
        if args.parallel == 0:
            args.parallel = optimal['parallel']
        
        # Language-specific optimization messages
        lang_names = {'ka': 'Georgian', 'ru': 'Russian', 'en': 'English'}
        lang_name = lang_names.get(args.lang, 'Unknown')
        print(f"TURBO MODE ENGAGED - {lang_name}")
        print(f"Strategy: {optimal['method']} generation, {args.parallel} workers")
        print(f"Processing: {len(text.split())} words, {len(text)} characters")
    
    # Set defaults if not specified
    if args.parallel == 0:
        args.parallel = min(4, OPTIMAL_WORKERS)
    
    async def run_generation():
        try:
            if args.chunk_seconds > 0 or len(text.split()) > 200:
                # Smart chunked generation
                await smart_generate_long_text(
                    text, args.lang,
                    chunk_seconds=args.chunk_seconds or 30,
                    parallel=args.parallel,
                    output_path=output_path
                )
            else:
                # Ultra-fast direct generation
                start = time.perf_counter()
                await fast_generate_audio(text, args.lang, output_path)
                elapsed = time.perf_counter() - start
                print(f"⚡ Completed in {elapsed:.2f}s (direct)")
            
            if not args.no_play:
                play_audio(output_path)
                
        finally:
            # Cleanup HTTP resources
            await cleanup_http()
    
    # Run with optimized event loop
    try:
        asyncio.run(run_generation())
    except KeyboardInterrupt:
        print("\n⚡ Generation cancelled")

if __name__ == "__main__":
    main()