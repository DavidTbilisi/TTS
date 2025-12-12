"""Audio generation and playback utilities."""

import os
import sys
from edge_tts import Communicate
from .not_reading import replace_not_readable

# Optional imports
try:
    from pydub import AudioSegment
    HAS_PYDUB = True
except ImportError:
    HAS_PYDUB = False


VOICE_MAP = {
    'ka': 'ka-GE-EkaNeural',
    'en': 'en-GB-SoniaNeural',
    'ru': 'ru-RU-SvetlanaNeural',
    'en-US': 'en-US-SteffanNeural'
}


async def generate_audio(text: str, language: str, output_path: str, 
                        use_cache: bool = False, quiet: bool = False) -> bool:
    """Generate audio from text using edge-tts. Returns True if successful."""
    voice = VOICE_MAP.get(language, 'en-GB-SoniaNeural')
    
    # Generate new audio
    try:
        clean_text = replace_not_readable(text)
        communicate = Communicate(clean_text, voice)
        await communicate.save(output_path)
        
        # Success
        if not quiet:
            print(f"Audio generated: {os.path.abspath(output_path)}")
        return True
        
    except Exception as e:
        if not quiet:
            print(f"Error generating audio: {e}")
        return False


def merge_audio_files(parts: list[str], output_path: str) -> None:
    """Merge multiple MP3 files into one."""
    if not parts:
        raise ValueError("No parts to merge")
    
    # Remove existing output
    if os.path.exists(output_path):
        os.remove(output_path)
    
    if HAS_PYDUB:
        combined = AudioSegment.from_mp3(parts[0])
        for part in parts[1:]:
            combined += AudioSegment.from_mp3(part)
        combined.export(output_path, format='mp3')
    else:
        # Fallback to ffmpeg
        listfile = '.ff_concat.txt'
        try:
            with open(listfile, 'w', encoding='utf-8') as f:
                for part in parts:
                    f.write(f"file '{os.path.abspath(part)}'\n")
            
            rc = os.system(f"ffmpeg -y -hide_banner -loglevel error -f concat -safe 0 -i {listfile} -c copy {output_path}")
            if rc != 0:
                raise RuntimeError('ffmpeg concat failed')
        finally:
            try:
                os.remove(listfile)
            except Exception:
                pass


def play_audio(file_path: str) -> None:
    """Play audio file using platform-specific commands."""
    try:
        abs_path = os.path.abspath(file_path)
        if sys.platform.startswith('win'):
            os.startfile(abs_path)
        elif sys.platform == 'darwin':
            os.system(f"open '{abs_path}' &")
        else:
            if os.system(f"xdg-open '{abs_path}' &") != 0:
                os.system(f"mpg123 '{abs_path}' &")
    except Exception:
        pass  # Best-effort playback