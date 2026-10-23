"""Live streaming TTS — read stdin as it arrives, speak sentence-by-sentence.

Designed for piping LLM/agent output:

    claude … | tts-ka --live --lang en

Each completed sentence is synthesized and queued to the existing
``StreamingAudioPlayer`` so playback starts within ~1s of the first sentence
landing. Sentences are detected on ``[.!?]`` + whitespace, paragraph breaks
(``\\n\\n``), or an idle timeout (default 800 ms) so the buffer never gets
stuck mid-thought. Abbreviations (``e.g.``, ``Dr.``, ``т.е.``), initials and
line-leading list markers (``1.``) do not end a sentence, and a run-on longer
than ``MAX_SENTENCE_CHARS`` is cut at a comma or space.

stdin is read in raw blocks rather than lines, so a long line is spoken as
its sentences complete instead of when its newline finally arrives.

Code fences (``\\`\\`\\``) are tracked: a sentence boundary inside an open
fence is held back until the closing fence arrives so the sanitizer can
collapse the whole block to "omitted fenced code block".
"""

from __future__ import annotations

import asyncio
import codecs
import os
import re
import sys
import tempfile
import threading
import time
from typing import AsyncIterator, Callable, List, Optional, Tuple

from .fast_audio import fast_generate_audio, generation_failed
from .not_reading import replace_not_readable
from .streaming_player import StreamingAudioPlayer

DEFAULT_IDLE_FLUSH_MS = 800
DEFAULT_MAX_CONCURRENT = 4

# `[.!?]+` optionally followed by a closing quote/bracket, then whitespace.
# Trailing whitespace is required so "Hello." mid-stream does not flush before
# the user finishes typing "Hello.com" — the space/newline is the real signal.
_SENTENCE_END_RE = re.compile(r"[.!?]+[\"')\]]?\s")
# Same, but also at the very end of the buffer (``feed(..., eager_end=True)``).
_SENTENCE_END_EAGER_RE = re.compile(r"[.!?]+[\"')\]]?(?:\s|$)")
_PARAGRAPH_END_RE = re.compile(r"\n\s*\n")
# Where an over-long sentence may be cut, best first.
_SOFT_BREAK_RES = (re.compile(r"[,;:]\s"), re.compile(r"\s"))

# A run-on with no sentence end is cut once it grows past this many characters.
MAX_SENTENCE_CHARS = 400

# Words that end in "." without ending the sentence (lowercase, final dot dropped).
_ABBREVIATIONS = frozenset({
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "e.g", "i.e",
    "fig", "inc", "ltd", "approx", "dept", "vol",
    "т.е", "т.д", "т.п", "т.к", "г", "гг", "ул", "др", "см", "напр",
    "ა.შ", "ძვ.წ",
})


def _word_before(text: str, end: int) -> Tuple[str, int]:
    """The run of letters, digits and dots ending at *end*, and where it starts."""
    i = end
    while i > 0 and (text[i - 1].isalnum() or text[i - 1] == "."):
        i -= 1
    return text[i:end], i


def _is_false_end(text: str, punct_start: int, punct: str) -> bool:
    """True when the "." at *punct_start* belongs to an abbreviation, initial or list marker."""
    if punct != ".":
        return False
    word, word_start = _word_before(text, punct_start)
    if not word:
        return False
    if word.lower() in _ABBREVIATIONS:
        return True
    if len(word) == 1 and word.isupper() and word != "I":
        return True  # an initial: "J. R. R. Tolkien"
    if word.isdigit():
        line_start = text.rfind("\n", 0, word_start) + 1
        return not text[line_start:word_start].strip()  # "1. First step"
    return False


class SentenceBuffer:
    """Accumulates streaming text and yields complete sentences.

    The buffer is fence-aware: while inside an unclosed ``\\`\\`\\``  fenced
    code block, no new sentences after the open fence are released until the
    closing fence arrives. Sentences before the open fence still flow.
    """

    def __init__(self, idle_flush_ms: int = DEFAULT_IDLE_FLUSH_MS) -> None:
        self._buf: str = ""
        self._last_input_at: float = time.monotonic()
        self.idle_flush_ms = idle_flush_ms

    @property
    def buffer(self) -> str:
        return self._buf

    def _fence_positions(self) -> List[int]:
        """Indices of every ``\\`\\`\\`` run in the buffer, in order."""
        out: List[int] = []
        start = 0
        while True:
            idx = self._buf.find("```", start)
            if idx == -1:
                break
            out.append(idx)
            start = idx + 3
        return out

    def _first_unmatched_fence(self) -> int:
        """Index of the first opened ``\\`\\`\\``  with no matching close, else -1."""
        positions = self._fence_positions()
        if len(positions) % 2 == 1:
            return positions[-1]
        return -1

    def _closed_fence_ranges(self) -> List[Tuple[int, int]]:
        """``[(open_start, close_end), ...]`` for every matched fence pair."""
        positions = self._fence_positions()
        pairs: List[Tuple[int, int]] = []
        for i in range(0, len(positions) - 1, 2):
            pairs.append((positions[i], positions[i + 1] + 3))
        return pairs

    @staticmethod
    def _inside_fence(pos: int, ranges: List[Tuple[int, int]]) -> int:
        """If *pos* lies inside any (start, end), return that end; else -1."""
        for start, end in ranges:
            if start <= pos < end:
                return end
        return -1

    def feed(self, text: str, eager_end: bool = False) -> List[str]:
        """Append *text*, return any complete sentences ready to speak.

        With *eager_end*, terminal punctuation at the very end of the buffer
        also ends a sentence. Use it when each feed is a complete message (MCP
        ``stream_append``) rather than an arbitrary slice of a byte stream.
        """
        if not text:
            return []
        self._buf += text
        self._last_input_at = time.monotonic()
        return self._extract(eager_end)

    def _next_boundary(self, start: int = 0, eager_end: bool = False) -> Optional[int]:
        """Return the end-index of the next sentence/paragraph boundary
        outside any closed fence and before any open fence, or ``None``."""
        open_at = self._first_unmatched_fence()
        ranges = self._closed_fence_ranges()
        sentence_re = _SENTENCE_END_EAGER_RE if eager_end else _SENTENCE_END_RE
        pos = start
        n = len(self._buf)
        while pos < n:
            m_sent = sentence_re.search(self._buf, pos)
            m_para = _PARAGRAPH_END_RE.search(self._buf, pos)
            candidates = [m for m in (m_sent, m_para) if m is not None]
            if not candidates:
                return None
            m = min(candidates, key=lambda x: x.end())
            if open_at >= 0 and m.start() >= open_at:
                return None  # past an unclosed fence — hold
            jump = self._inside_fence(m.start(), ranges)
            if jump != -1:
                pos = jump  # boundary fell inside a closed fence; look past it
                continue
            if m is m_sent and _is_false_end(self._buf, m.start(), m.group().rstrip("\"')] \t\r\n")):
                pos = m.end() if m.end() > m.start() else m.start() + 1
                continue
            return m.end()
        return None

    def _overflow_cut(self) -> Optional[int]:
        """Cut point for a run-on longer than ``MAX_SENTENCE_CHARS``, else ``None``.

        Never cuts near code fences: those must reach the sanitizer whole.
        """
        if len(self._buf) <= MAX_SENTENCE_CHARS or "```" in self._buf[:MAX_SENTENCE_CHARS + 3]:
            return None
        head = self._buf[:MAX_SENTENCE_CHARS]
        for break_re in _SOFT_BREAK_RES:
            ends = [m.end() for m in break_re.finditer(head)]
            if ends and ends[-1] > MAX_SENTENCE_CHARS // 4:
                return ends[-1]
        return MAX_SENTENCE_CHARS

    def _extract(self, eager_end: bool = False) -> List[str]:
        out: List[str] = []
        while True:
            cut = self._next_boundary(eager_end=eager_end)
            if cut is None:
                cut = self._overflow_cut()
            if cut is None:
                break
            piece = self._buf[:cut].strip()
            self._buf = self._buf[cut:]
            if piece:
                out.append(piece)
        return out

    def time_since_last_input_ms(self, now: Optional[float] = None) -> float:
        now = now if now is not None else time.monotonic()
        return (now - self._last_input_at) * 1000.0

    def should_idle_flush(self, now: Optional[float] = None) -> bool:
        """True when the buffer has non-empty content older than ``idle_flush_ms``.

        Does not fire while a code fence is open — that text isn't speakable
        until the close arrives. EOF drain (``drain(force=True)``) handles the
        truly-stuck case.
        """
        if self._first_unmatched_fence() >= 0:
            return False
        if not self._buf.strip():
            return False
        return self.time_since_last_input_ms(now) >= self.idle_flush_ms

    def drain(self, force: bool = False) -> Optional[str]:
        """Return the buffered remainder, clearing it. Returns ``None`` if empty.

        Without *force*, holds back when a code fence is still open. With
        *force=True* (EOF), returns whatever is in the buffer.
        """
        if not force and self._first_unmatched_fence() >= 0:
            return None
        text = self._buf.strip()
        self._buf = ""
        if not text:
            return None
        return text


# Async iterator yielding either a text chunk or ``None`` to signal EOF.
InputReader = AsyncIterator[Optional[str]]
# Coroutine: (text, lang, output_path, *, voice, prosody); signals failure by
# returning ``False`` (like ``fast_generate_audio``) or raising.
AudioGenerator = Callable


async def _stdin_pump(queue: "asyncio.Queue[Optional[str]]", fd: Optional[int] = None) -> None:
    """Forward stdin (or file descriptor *fd*) to *queue* via a daemon thread.

    Reads raw blocks as soon as they arrive (``os.read`` returns whatever is
    available) and decodes them incrementally, so a UTF-8 character split
    across two reads (Georgian is 3 bytes per letter) is never mangled.
    Falls back to line iteration when stdin has no file descriptor. Pushes
    ``None`` on EOF.
    """
    loop = asyncio.get_running_loop()

    def put(item: Optional[str]) -> None:
        asyncio.run_coroutine_threadsafe(queue.put(item), loop)

    def _reader() -> None:
        try:
            src = fd
            if src is None:
                try:
                    src = sys.stdin.fileno()
                except (AttributeError, OSError, ValueError):
                    for line in sys.stdin:
                        put(line)
                    return
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            while True:
                data = os.read(src, 4096)
                text = decoder.decode(data, final=not data)
                if text:
                    put(text.replace("\r\n", "\n"))
                if not data:
                    return
        except OSError:
            pass
        finally:
            put(None)

    threading.Thread(target=_reader, daemon=True).start()


async def live_loop(
    *,
    lang: str = "en",
    voice: Optional[str] = None,
    prosody=None,
    idle_flush_ms: int = DEFAULT_IDLE_FLUSH_MS,
    show_player_gui: bool = False,
    sanitize: bool = True,
    max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    input_reader: Optional[InputReader] = None,
    audio_generator: Optional[AudioGenerator] = None,
    player: Optional[StreamingAudioPlayer] = None,
    tmp_dir: Optional[str] = None,
) -> None:
    """Read text and speak it sentence-by-sentence as it arrives.

    Production: pass nothing (stdin + StreamingAudioPlayer + fast_generate_audio).
    Tests: inject ``input_reader``, ``audio_generator``, and/or ``player``.
    """
    buf = SentenceBuffer(idle_flush_ms=idle_flush_ms)
    owns_tmp = tmp_dir is None
    tmp_dir = tmp_dir or tempfile.mkdtemp(prefix="ttska-live-")
    owns_player = player is None
    if player is None:
        player = StreamingAudioPlayer(show_gui=show_player_gui)
    gen = audio_generator or fast_generate_audio

    chunk_index = 0
    pending: List[asyncio.Task] = []
    sem = asyncio.Semaphore(max_concurrent)

    player.start()

    async def speak(sentence: str) -> None:
        nonlocal chunk_index
        idx = chunk_index
        chunk_index += 1
        added = False
        try:
            text = replace_not_readable(sentence) if sanitize else sentence
            if not text.strip():
                return
            async with sem:
                path = os.path.join(tmp_dir, f".part_{idx:04d}.mp3")
                try:
                    if await gen(text, lang, path, voice=voice, prosody=prosody) is False:
                        raise generation_failed("synthesis failed")
                    player.add_chunk(path, chunk_index=idx)
                    added = True
                except Exception as exc:  # noqa: BLE001 — surface to user, keep going
                    print(f"⚠️  Could not speak sentence {idx}: {exc}",
                          file=sys.stderr)
        finally:
            if not added:
                # Later sentences must not wait for one that will never play.
                player.skip_index(idx)

    def _spawn(s: str) -> None:
        pending.append(asyncio.create_task(speak(s)))

    # Build the input source.
    if input_reader is None:
        queue: "asyncio.Queue[Optional[str]]" = asyncio.Queue()
        await _stdin_pump(queue)

        async def _iter() -> InputReader:  # type: ignore[misc]
            timeout_s = idle_flush_ms / 1000.0
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=timeout_s)
                except asyncio.TimeoutError:
                    yield ""  # idle marker
                    continue
                yield item
                if item is None:
                    return

        input_reader = _iter()  # type: ignore[assignment]

    interrupted = False
    try:
        async for chunk in input_reader:
            if chunk is None:
                break
            if chunk == "":
                # Idle marker from the production pump.
                if buf.should_idle_flush():
                    tail = buf.drain()
                    if tail:
                        _spawn(tail)
                continue
            for s in buf.feed(chunk):
                _spawn(s)

        # EOF: drain remainder, force past any unclosed fence.
        tail = buf.drain(force=True)
        if tail:
            _spawn(tail)

        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    except BaseException:
        # Ctrl+C / cancellation: silence now instead of playing out the queue.
        interrupted = True
        for task in pending:
            task.cancel()
        raise
    finally:
        try:
            if interrupted:
                player.stop()
            else:
                player.finish_generation()
        except Exception:
            pass
        if owns_player and not interrupted:
            try:
                # Blocks until mpv/VLC are done with the files deleted below.
                await asyncio.to_thread(player.wait_until_released)
            except Exception:
                pass
        if owns_tmp:
            try:
                import shutil
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
