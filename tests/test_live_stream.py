"""Tests for the AI-friendly --live streaming mode.

SentenceBuffer is tested directly. live_loop is tested with injected fakes
(input_reader, audio_generator, player) so no real audio is generated.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import AsyncIterator, List, Optional
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from TTS_ka.live_stream import (  # noqa: E402
    DEFAULT_IDLE_FLUSH_MS,
    SentenceBuffer,
    live_loop,
)


# ── SentenceBuffer ───────────────────────────────────────────────────────────


class TestSentenceBuffer:
    def test_empty_feed_returns_empty(self):
        buf = SentenceBuffer()
        assert buf.feed("") == []

    def test_no_terminator_holds(self):
        buf = SentenceBuffer()
        assert buf.feed("Hello world") == []
        assert buf.buffer == "Hello world"

    def test_period_without_trailing_space_holds(self):
        """`Hello.` alone could be the start of `Hello.com` — must wait."""
        buf = SentenceBuffer()
        assert buf.feed("Hello.") == []

    def test_period_plus_space_flushes(self):
        buf = SentenceBuffer()
        assert buf.feed("Hello world. ") == ["Hello world."]

    def test_question_mark(self):
        buf = SentenceBuffer()
        assert buf.feed("Are you there? ") == ["Are you there?"]

    def test_exclamation(self):
        buf = SentenceBuffer()
        assert buf.feed("Wow! ") == ["Wow!"]

    def test_multiple_sentences_one_feed(self):
        buf = SentenceBuffer()
        out = buf.feed("One. Two! Three? Four. ")
        assert out == ["One.", "Two!", "Three?", "Four."]

    def test_partial_then_complete(self):
        buf = SentenceBuffer()
        assert buf.feed("Hello ") == []
        assert buf.feed("world. ") == ["Hello world."]

    def test_newline_counts_as_whitespace(self):
        buf = SentenceBuffer()
        assert buf.feed("Hello world.\n") == ["Hello world."]

    def test_paragraph_break_flushes_unterminated(self):
        buf = SentenceBuffer()
        out = buf.feed("Some prose without terminator\n\nNext bit")
        assert out == ["Some prose without terminator"]
        assert "Next bit" in buf.buffer

    def test_trailing_quote_allowed(self):
        buf = SentenceBuffer()
        assert buf.feed('She said "hi." ') == ['She said "hi."']

    def test_open_fence_holds_post_fence_content(self):
        """Sentences before an open fence flow; sentences after are held."""
        buf = SentenceBuffer()
        out = buf.feed("Prelude here. ```python\nx = 1\n")
        assert out == ["Prelude here."]
        # Even content with a sentence ender inside the fence stays buffered.
        out2 = buf.feed("# end. ")
        assert out2 == []

    def test_closing_fence_releases_buffer(self):
        buf = SentenceBuffer()
        buf.feed("Prelude here. ```python\nx = 1\n# end. ")
        out = buf.feed("```\nAfter the code. ")
        assert len(out) == 1
        assert "After the code." in out[0]

    def test_drain_empty_returns_none(self):
        buf = SentenceBuffer()
        assert buf.drain() is None

    def test_drain_returns_partial(self):
        buf = SentenceBuffer()
        buf.feed("Unfinished thought")
        assert buf.drain() == "Unfinished thought"
        assert buf.drain() is None

    def test_drain_holds_open_fence_without_force(self):
        buf = SentenceBuffer()
        buf.feed("```python\nx = 1\n")
        assert buf.drain() is None
        assert buf.buffer  # still there

    def test_drain_force_releases_open_fence(self):
        buf = SentenceBuffer()
        buf.feed("```python\nx = 1\n")
        out = buf.drain(force=True)
        assert out is not None
        assert "x = 1" in out

    def test_should_idle_flush_negative_when_empty(self):
        buf = SentenceBuffer(idle_flush_ms=50)
        assert not buf.should_idle_flush()

    def test_should_idle_flush_after_timeout(self):
        buf = SentenceBuffer(idle_flush_ms=20)
        buf.feed("partial")
        assert not buf.should_idle_flush()
        time.sleep(0.05)
        assert buf.should_idle_flush()

    def test_should_idle_flush_blocked_by_open_fence(self):
        buf = SentenceBuffer(idle_flush_ms=10)
        buf.feed("```code")
        time.sleep(0.03)
        # Idle flush must not fire while a fence is still open.
        assert not buf.should_idle_flush()


# ── live_loop ─────────────────────────────────────────────────────────────────


async def _reader_from(items: List[Optional[str]]) -> AsyncIterator[Optional[str]]:
    for it in items:
        yield it


def _fake_player() -> MagicMock:
    """A MagicMock standing in for StreamingAudioPlayer."""
    p = MagicMock()
    p.start = MagicMock()
    p.add_chunk = MagicMock()
    p.finish_generation = MagicMock()
    p.wait_for_completion = MagicMock()
    return p


def _async_audio_recorder():
    """Return (async_fn, recorded_calls).

    Each call appends (text, lang, output_path, voice, prosody).
    """
    calls: list = []

    async def gen(text, lang, output_path, *, voice=None, prosody=None):
        calls.append((text, lang, output_path, voice, prosody))
        # Touch the file so player.add_chunk() doesn't reject it.
        with open(output_path, "wb") as f:
            f.write(b"x")
    return gen, calls


class TestLiveLoop:
    @pytest.mark.asyncio
    async def test_speaks_each_sentence_in_order(self, temp_dir):
        gen, calls = _async_audio_recorder()
        player = _fake_player()
        reader = _reader_from([
            "First sentence. ",
            "Second one! ",
            "Third? ",
            None,
        ])
        await live_loop(
            lang="en",
            input_reader=reader,
            audio_generator=gen,
            player=player,
            tmp_dir=temp_dir,
        )
        spoken = [c[0] for c in calls]
        assert spoken == ["First sentence.", "Second one!", "Third?"]
        assert player.start.called
        assert player.finish_generation.called

    @pytest.mark.asyncio
    async def test_eof_drains_partial(self, temp_dir):
        gen, calls = _async_audio_recorder()
        player = _fake_player()
        reader = _reader_from(["Incomplete tail without terminator", None])
        await live_loop(
            lang="en",
            input_reader=reader,
            audio_generator=gen,
            player=player,
            tmp_dir=temp_dir,
        )
        assert len(calls) == 1
        assert "Incomplete tail" in calls[0][0]

    @pytest.mark.asyncio
    async def test_lang_and_voice_propagate(self, temp_dir):
        gen, calls = _async_audio_recorder()
        player = _fake_player()
        reader = _reader_from(["Hello. ", None])
        await live_loop(
            lang="ka",
            voice="ka-GE-EkaNeural",
            input_reader=reader,
            audio_generator=gen,
            player=player,
            tmp_dir=temp_dir,
        )
        assert calls[0][1] == "ka"
        assert calls[0][3] == "ka-GE-EkaNeural"

    @pytest.mark.asyncio
    async def test_player_receives_chunk_indices(self, temp_dir):
        gen, _ = _async_audio_recorder()
        player = _fake_player()
        reader = _reader_from(["A. ", "B. ", "C. ", None])
        await live_loop(
            lang="en",
            input_reader=reader,
            audio_generator=gen,
            player=player,
            tmp_dir=temp_dir,
        )
        indices = sorted(c.kwargs["chunk_index"] for c in player.add_chunk.call_args_list)
        assert indices == [0, 1, 2]

    @pytest.mark.asyncio
    async def test_sanitizer_strips_code_block(self, temp_dir):
        """When the closing fence arrives, the whole fence collapses to a placeholder."""
        gen, calls = _async_audio_recorder()
        player = _fake_player()
        reader = _reader_from([
            "Setup. ```python\nbad = 'syntax noise'\n```\nDone. ",
            None,
        ])
        await live_loop(
            lang="en",
            input_reader=reader,
            audio_generator=gen,
            player=player,
            tmp_dir=temp_dir,
        )
        spoken = " ".join(c[0] for c in calls)
        assert "syntax noise" not in spoken
        assert "Setup." in spoken
        assert "Done." in spoken

    @pytest.mark.asyncio
    async def test_empty_input_does_not_call_generator(self, temp_dir):
        gen, calls = _async_audio_recorder()
        player = _fake_player()
        await live_loop(
            lang="en",
            input_reader=_reader_from([None]),
            audio_generator=gen,
            player=player,
            tmp_dir=temp_dir,
        )
        assert calls == []
        assert player.finish_generation.called

    @pytest.mark.asyncio
    async def test_whitespace_only_input_does_not_speak(self, temp_dir):
        gen, calls = _async_audio_recorder()
        player = _fake_player()
        await live_loop(
            lang="en",
            input_reader=_reader_from(["   \n\n  ", None]),
            audio_generator=gen,
            player=player,
            tmp_dir=temp_dir,
        )
        assert calls == []

    @pytest.mark.asyncio
    async def test_generator_exception_is_swallowed_per_sentence(self, temp_dir, capsys):
        player = _fake_player()
        call_count = {"n": 0}

        async def flaky_gen(text, lang, output_path, *, voice=None, prosody=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("boom")
            with open(output_path, "wb") as f:
                f.write(b"x")

        await live_loop(
            lang="en",
            input_reader=_reader_from(["One. ", "Two. ", None]),
            audio_generator=flaky_gen,
            player=player,
            tmp_dir=temp_dir,
        )
        # Both sentences attempted; the second succeeds.
        assert call_count["n"] == 2
        # add_chunk only called for the successful second one
        assert player.add_chunk.call_count == 1
        err = capsys.readouterr().err
        assert "Could not speak" in err
