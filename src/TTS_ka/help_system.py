"""Comprehensive help system with examples and detailed usage information."""

import sys
from typing import List, Dict

# Language information with flags and descriptions
LANGUAGE_INFO = {
    'ka': {'flag': '🇬🇪', 'name': 'Georgian', 'voice': 'ka-GE-EkaNeural', 'desc': 'High-quality Georgian neural voice'},
    'ru': {'flag': '🇷🇺', 'name': 'Russian', 'voice': 'ru-RU-SvetlanaNeural', 'desc': 'Fast Russian neural voice'},
    'en': {'flag': '🇬🇧', 'name': 'English', 'voice': 'en-GB-SoniaNeural', 'desc': 'Premium English neural voice'}
}

def print_banner():
    """Print application banner."""
    print()
    print("=" * 80)
    print("                    ULTRA-FAST TTS SYSTEM                     ")
    print("              Maximum Speed Text-to-Speech Generator                   ")
    print("              Supports: Georgian | Russian | English                   ")
    print("=" * 80)
    print()

def print_languages():
    """Print supported languages with details."""
    print("SUPPORTED LANGUAGES:")
    print("=" * 50)
    for code, info in LANGUAGE_INFO.items():
        print(f"  {info['flag']} {code:2s} - {info['name']:8s} ({info['desc']})")
    print()

def print_performance_guide():
    """Print performance optimization guide."""
    print("PERFORMANCE GUIDE:")
    print("=" * 50)
    print("Speed Comparison (1000 words):")
    print("  * Direct Generation:    ~15-25 seconds")
    print("  * Turbo Mode:          ~8-15 seconds")
    print("  * Chunked (4 workers): ~6-12 seconds")
    print()
    print("Optimization Tips:")
    print("  * Use --turbo for automatic optimization")
    print("  * For long texts: --chunk-seconds 30 --parallel 6")
    print("  * For short texts: direct generation (fastest)")
    print("  * Georgian (ka): Slightly slower but premium quality")
    print("  * Russian/English: Maximum speed")
    print()

def print_basic_examples():
    """Print basic usage examples."""
    print("📖 BASIC EXAMPLES:")
    print("═" * 50)
    
    examples = [
        {
            'desc': 'Simple text generation',
            'cmd': 'python -m TTS_ka "Hello world" --lang en',
            'note': 'Direct text input, English voice'
        },
        {
            'desc': 'Georgian text with auto-play disabled',
            'cmd': 'python -m TTS_ka "გამარჯობა მსოფლიო" --lang ka --no-play',
            'note': 'Georgian text, no automatic playback'
        },
        {
            'desc': 'Russian from file',
            'cmd': 'python -m TTS_ka russian_text.txt --lang ru',
            'note': 'Read text from file, Russian voice'
        },
        {
            'desc': 'From clipboard (fastest workflow)',
            'cmd': 'python -m TTS_ka clipboard --lang en',
            'note': 'Convert clipboard content instantly'
        }
    ]
    
    for i, ex in enumerate(examples, 1):
        print(f"{i}. {ex['desc']}:")
        print(f"   $ {ex['cmd']}")
        print(f"   💡 {ex['note']}")
        print()

def print_advanced_examples():
    """Print advanced usage examples."""
    print("🔥 ADVANCED EXAMPLES:")
    print("═" * 50)
    
    examples = [
        {
            'desc': 'Maximum speed mode (recommended)',
            'cmd': 'python -m TTS_ka long_document.txt --turbo --lang en',
            'note': 'Auto-optimizes chunk size and workers for maximum speed'
        },
        {
            'desc': 'Custom chunking for very long texts',
            'cmd': 'python -m TTS_ka book.txt --chunk-seconds 45 --parallel 8 --lang ru',
            'note': '45-second chunks with 8 parallel workers'
        },
        {
            'desc': 'Batch processing workflow',
            'cmd': 'for file in *.txt; do python -m TTS_ka "$file" --turbo --no-play; done',
            'note': 'Process multiple files without playback'
        },
        {
            'desc': 'Integration with clipboard (Windows/AutoHotkey)',
            'cmd': 'python -m TTS_ka clipboard --turbo --lang ka',
            'note': 'Perfect for AutoHotkey automation'
        }
    ]
    
    for i, ex in enumerate(examples, 1):
        print(f"{i}. {ex['desc']}:")
        print(f"   $ {ex['cmd']}")
        print(f"   🎯 {ex['note']}")
        print()

def print_workflow_guide():
    """Print recommended workflows."""
    print("🔄 RECOMMENDED WORKFLOWS:")
    print("═" * 50)
    
    workflows = [
        {
            'name': 'Quick Text Conversion',
            'steps': [
                'Copy text to clipboard',
                'Run: python -m TTS_ka clipboard --turbo --lang en',
                'Audio plays automatically'
            ],
            'time': '~3-8 seconds'
        },
        {
            'name': 'Long Document Processing',
            'steps': [
                'Save text as .txt file',
                'Run: python -m TTS_ka document.txt --turbo --lang ru',
                'Watch rich progress with ETA',
                'Get high-quality MP3 output'
            ],
            'time': '~2-4x faster than real-time'
        },
        {
            'name': 'Multi-language Batch',
            'steps': [
                'Prepare text files: en.txt, ru.txt, ka.txt',
                'Process each with appropriate --lang flag',
                'Use --no-play for batch processing',
                'Combine or organize output files'
            ],
            'time': 'Depends on total word count'
        }
    ]
    
    for workflow in workflows:
        print(f"📋 {workflow['name']} ({workflow['time']}):")
        for i, step in enumerate(workflow['steps'], 1):
            print(f"   {i}. {step}")
        print()

def print_troubleshooting():
    """Print troubleshooting guide."""
    print("🔧 TROUBLESHOOTING:")
    print("═" * 50)
    
    issues = [
        {
            'problem': 'Slow generation speed',
            'solutions': [
                'Use --turbo flag for auto-optimization',
                'Increase --parallel workers (try 4-8)',
                'Check internet connection speed',
                'Use shorter --chunk-seconds (20-30)'
            ]
        },
        {
            'problem': 'Language not working',
            'solutions': [
                'Verify language code: ka, ru, or en only',
                'Check text encoding (UTF-8 recommended)',
                'For Georgian: ensure proper Unicode text',
                'Try with simple ASCII text first'
            ]
        },
        {
            'problem': 'File not found errors',
            'solutions': [
                'Use absolute file paths',
                'Check file exists and is readable',
                'Ensure UTF-8 encoding for text files',
                'Try "clipboard" instead of file input'
            ]
        },
        {
            'problem': 'No audio playback',
            'solutions': [
                'Check data.mp3 file is created',
                'Use --no-play and manually open file',
                'Verify system audio/MP3 support',
                'Try different media player'
            ]
        }
    ]
    
    for issue in issues:
        print(f"❓ {issue['problem']}:")
        for solution in issue['solutions']:
            print(f"   ✓ {solution}")
        print()

def show_comprehensive_help():
    """Display comprehensive help with all sections."""
    print_banner()
    print_languages()
    print_performance_guide()
    print_basic_examples()
    print_advanced_examples()
    print_workflow_guide()
    print_troubleshooting()
    
    print("📚 ADDITIONAL RESOURCES:")
    print("═" * 50)
    print("  • GitHub: https://github.com/YourRepo/TTS_ka")
    print("  • Documentation: Run with --help for quick reference")
    print("  • AutoHotkey Integration: See read.ahk examples")
    print("  • Performance Benchmarks: Use --turbo for optimal settings")
    print()
    
    print("💡 PRO TIPS:")
    print("  • Always use --turbo for best performance")
    print("  • Georgian text works best with Unicode UTF-8")
    print("  • For automation: combine with --no-play flag")
    print("  • Watch the rich progress display for real-time stats")
    print()

def show_quick_help():
    """Show condensed help information."""
    print_banner()
    print("🚀 QUICK START:")
    print("  python -m TTS_ka 'your text' --turbo --lang en")
    print("  python -m TTS_ka clipboard --turbo --lang ka")
    print("  python -m TTS_ka file.txt --turbo --lang ru")
    print()
    print("📋 Languages: ka (Georgian), ru (Russian), en (English)")
    print("⚡ Use --turbo for maximum speed")
    print("📖 Use --help-full for comprehensive guide with examples")
    print()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--full":
        show_comprehensive_help()
    else:
        show_quick_help()