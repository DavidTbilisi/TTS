"""Fast audio generation using optimized HTTP client and streaming."""

import os
import sys
import asyncio
from typing import Optional
import httpx
try:
    import uvloop
    HAS_UVLOOP = True
except ImportError:
    HAS_UVLOOP = False

try:
    import soundfile as sf
    HAS_SOUNDFILE = True
except ImportError:
    HAS_SOUNDFILE = False

# Cache functionality removed

# Optimized voice selection for maximum speed - ka/ru/en only
VOICE_MAP = {
    'ka': 'ka-GE-EkaNeural',    # Georgian - Premium quality
    'ru': 'ru-RU-SvetlanaNeural',  # Russian - Fast neural voice
    'en': 'en-GB-SoniaNeural'      # English - Fastest neural voice
}

# Global HTTP client for connection reuse
_http_client: Optional[httpx.AsyncClient] = None

async def get_http_client() -> httpx.AsyncClient:
    """Get or create optimized HTTP client with connection pooling."""
    global _http_client
    if _http_client is None:
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=100)
        timeout = httpx.Timeout(30.0, connect=10.0)
        _http_client = httpx.AsyncClient(
            limits=limits, 
            timeout=timeout,
            http2=True  # Enable HTTP/2 for better performance
        )
    return _http_client


async def fast_generate_audio(text: str, language: str, output_path: str, 
                             quiet: bool = False) -> bool:
    """Ultra-fast audio generation with optimized HTTP."""
    
    # Set faster event loop if available
    if HAS_UVLOOP and sys.platform != 'win32':
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    
    voice = VOICE_MAP.get(language)
    if not voice:
        if not quiet:
            print(f"❌ Language '{language}' not supported. Use: ka, ru, en")
        return False
    
    try:
        # Use optimized HTTP client instead of edge-tts
        client = await get_http_client()
        
        # Generate SSML
        ssml = f"""<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>
            <voice name='{voice}'>{text}</voice>
        </speak>"""
        
        # Direct API call to Azure Cognitive Services TTS
        headers = {
            'Content-Type': 'application/ssml+xml',
            'X-Microsoft-OutputFormat': 'audio-16khz-128kbitrate-mono-mp3',
            'User-Agent': 'Mozilla/5.0'
        }
        
        # Fast streaming download
        url = "https://speech.platform.bing.com/synthesize"
        
        async with client.stream('POST', url, headers=headers, content=ssml.encode()) as response:
            if response.status_code == 200:
                # Stream directly to file for fastest I/O
                with open(output_path, 'wb') as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
                
                if not quiet:
                    print(f"⚡ Generated: {os.path.abspath(output_path)}")
                return True
            else:
                # Fallback to edge-tts if direct API fails
                return await fallback_generate_audio(text, language, output_path, quiet)
                
    except Exception:
        # Fallback to edge-tts 
        return await fallback_generate_audio(text, language, output_path, quiet)


async def fallback_generate_audio(text: str, language: str, output_path: str, 
                                 quiet: bool = False) -> bool:
    """Fallback to edge-tts if fast method fails."""
    try:
        from edge_tts import Communicate
        voice = VOICE_MAP.get(language)
        if not voice:
            if not quiet:
                print(f"❌ Language '{language}' not supported. Use: ka, ru, en")
            return False
        
        communicate = Communicate(text, voice)
        await communicate.save(output_path)
        
        if not quiet:
            print(f"Generated (fallback): {os.path.abspath(output_path)}")
        return True
    except Exception as e:
        if not quiet:
            print(f"Error generating audio: {e}")
        return False


def fast_merge_audio_files(parts: list[str], output_path: str) -> None:
    """Ultra-fast audio merging using soundfile when available."""
    if not parts:
        raise ValueError("No parts to merge")
    
    # Remove existing output
    if os.path.exists(output_path):
        os.remove(output_path)
    
    if HAS_SOUNDFILE and len(parts) > 1:
        try:
            # Use soundfile for fastest concatenation
            import numpy as np
            
            combined_data = []
            sample_rate = None
            
            for part in parts:
                try:
                    data, sr = sf.read(part)
                    if sample_rate is None:
                        sample_rate = sr
                    combined_data.append(data)
                except Exception:
                    # Fallback for this part
                    continue
            
            if combined_data and sample_rate:
                final_audio = np.concatenate(combined_data, axis=0)
                sf.write(output_path, final_audio, sample_rate)
                return
        except Exception:
            pass  # Fall through to other methods
    
    # Fallback to existing methods
    try:
        from pydub import AudioSegment
        combined = AudioSegment.from_mp3(parts[0])
        for part in parts[1:]:
            combined += AudioSegment.from_mp3(part)
        combined.export(output_path, format='mp3')
    except ImportError:
        # FFmpeg fallback
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
    """Fast audio playback with platform optimization."""
    try:
        abs_path = os.path.abspath(file_path)
        if sys.platform.startswith('win'):
            # Fastest Windows playback
            os.startfile(abs_path)
        elif sys.platform == 'darwin':
            os.system(f"open '{abs_path}' &")
        else:
            # Linux - try multiple fast players
            for cmd in [f"mpv '{abs_path}' &", f"vlc '{abs_path}' &", f"xdg-open '{abs_path}' &"]:
                if os.system(cmd) == 0:
                    break
    except Exception:
        pass


async def cleanup_http():
    """Clean up HTTP client resources."""
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None