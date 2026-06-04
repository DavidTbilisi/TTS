"""Synchronized RSVP + audio reader (study mode).

Opens a Tk window that flashes one word at a time at the center, with faded
peripheral context on each side, while the same text plays through
:mod:`pygame.mixer`. The sync loop polls the audio position every ~33 ms and
looks up the current word via :class:`study_session.StudySession`.

The pygame import is lazy so non-study users of TTS_ka do not pay for it.
This module is excluded from coverage (UI), the same convention used for
:mod:`gui.py`.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable, Optional

from .fast_audio import generate_audio_with_subs
from .prosody import ProsodyOpts
from .quiz import QuizProvider, RuleBasedProvider
from . import session_log
from .study_session import StudySession


POLL_INTERVAL_MS = 33  # ~30 Hz; smooth without flooding the event loop
PERIPHERAL_SPAN = 3


def _text_hash(text: str, voice: str, rate: str) -> str:
    h = hashlib.sha256()
    h.update(text.encode("utf-8"))
    h.update(b"\x00")
    h.update(voice.encode("utf-8"))
    h.update(b"\x00")
    h.update(rate.encode("utf-8"))
    return h.hexdigest()[:16]


def _cache_dir() -> Path:
    p = Path(tempfile.gettempdir()) / "tts_ka_study"
    p.mkdir(parents=True, exist_ok=True)
    return p


class StudyPlayer:
    """Tk + pygame window that drives one synchronized study session."""

    def __init__(
        self,
        text: str,
        language: str = "en",
        rate: str = "+0%",
        chunk_size_words: int = 200,
        quiz_provider: Optional[QuizProvider] = None,
    ) -> None:
        self.text = text
        self.language = language
        self.rate = rate
        self.chunk_size_words = chunk_size_words
        self.quiz_provider: QuizProvider = quiz_provider or RuleBasedProvider()

        self.session: Optional[StudySession] = None
        self.audio_path: Optional[Path] = None
        self._pygame = None
        self._playing = False
        self._play_started_pos_ms = 0  # offset from a seek, since get_pos() is play-relative

        self.root = tk.Tk()
        self.root.title("TTS_ka — Study Mode")
        self.root.geometry("900x320")
        self._build_ui()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        self.status_var = tk.StringVar(value="Generating audio + timings…")
        ttk.Label(outer, textvariable=self.status_var, foreground="#666").pack(anchor="w")

        row = ttk.Frame(outer)
        row.pack(fill=tk.X, pady=24)
        self.prev_var = tk.StringVar(value="")
        self.current_var = tk.StringVar(value="—")
        self.next_var = tk.StringVar(value="")
        ttk.Label(row, textvariable=self.prev_var, foreground="#999", font=("TkDefaultFont", 14)).pack(side=tk.LEFT, expand=True)
        ttk.Label(row, textvariable=self.current_var, font=("TkDefaultFont", 48, "bold")).pack(side=tk.LEFT, expand=True)
        ttk.Label(row, textvariable=self.next_var, foreground="#999", font=("TkDefaultFont", 14)).pack(side=tk.LEFT, expand=True)

        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X, pady=8)
        self.play_btn = ttk.Button(controls, text="Play", command=self._toggle_play, state=tk.DISABLED)
        self.play_btn.pack(side=tk.LEFT)
        ttk.Button(controls, text="◀ Chunk", command=lambda: self._jump_chunk(-1)).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Chunk ▶", command=lambda: self._jump_chunk(+1)).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Quiz me", command=self._show_quiz).pack(side=tk.LEFT, padx=12)
        ttk.Button(controls, text="Save session", command=self._save_session).pack(side=tk.RIGHT)

    def launch(self) -> None:
        """Generate audio in a worker thread, then run the Tk mainloop."""
        threading.Thread(target=self._prepare_audio, daemon=True).start()
        self.root.mainloop()

    def _prepare_audio(self) -> None:
        try:
            cache_dir = _cache_dir()
            digest = _text_hash(self.text, self.language, self.rate)
            audio_path = cache_dir / f"{digest}.mp3"
            prosody = ProsodyOpts(rate=self.rate)
            events = asyncio.run(
                generate_audio_with_subs(
                    self.text, self.language, str(audio_path), prosody=prosody
                )
            )
        except Exception as exc:  # narrow surface, surfaced to UI
            self.root.after(0, lambda: self.status_var.set(f"Generation failed: {exc}"))
            return

        self.audio_path = audio_path
        self.session = StudySession(events, chunk_size_words=self.chunk_size_words)
        self.root.after(0, self._on_audio_ready)

    def _on_audio_ready(self) -> None:
        try:
            import pygame  # lazy import
            pygame.mixer.init()
            pygame.mixer.music.load(str(self.audio_path))
            self._pygame = pygame
        except Exception as exc:
            self.status_var.set(f"Audio backend init failed: {exc}")
            return
        wpm = self.session.wpm if self.session else 0.0
        self.status_var.set(f"Ready — {len(self.session.events) if self.session else 0} words, ~{wpm:.0f} wpm. Press Play.")
        self.play_btn.config(state=tk.NORMAL)

    def _toggle_play(self) -> None:
        if not self._pygame or not self.session:
            return
        if not self._playing:
            self._pygame.mixer.music.play(start=self._play_started_pos_ms / 1000.0)
            self._playing = True
            self.play_btn.config(text="Pause")
            self._schedule_poll()
        else:
            self._pygame.mixer.music.pause()
            self._playing = False
            self.play_btn.config(text="Play")

    def _schedule_poll(self) -> None:
        if not self._playing:
            return
        self._poll_position()
        self.root.after(POLL_INTERVAL_MS, self._schedule_poll)

    def _poll_position(self) -> None:
        if not self._pygame or not self.session:
            return
        rel_ms = self._pygame.mixer.music.get_pos()
        if rel_ms < 0:
            return
        pos_ms = self._play_started_pos_ms + rel_ms
        if pos_ms >= self.session.total_duration_ms:
            self._playing = False
            self.play_btn.config(text="Play")
            return
        view = self.session.peripheral(pos_ms, span=PERIPHERAL_SPAN)
        self.prev_var.set(" ".join(ev.text for ev in view.prev))
        self.current_var.set(view.current.text if view.current else "—")
        self.next_var.set(" ".join(ev.text for ev in view.next))

    def _jump_chunk(self, delta: int) -> None:
        if not self._pygame or not self.session:
            return
        rel_ms = self._pygame.mixer.music.get_pos()
        pos_ms = max(0, self._play_started_pos_ms + (rel_ms if rel_ms >= 0 else 0))
        cur = self.session.chunk_index_at(pos_ms)
        target = max(0, min(len(self.session.chunk_boundaries()) - 1, cur + delta))
        new_pos_ms = self.session.chunk_start_ms(target)
        self._play_started_pos_ms = new_pos_ms
        was_playing = self._playing
        self._pygame.mixer.music.stop()
        self._playing = False
        if was_playing:
            self._toggle_play()

    def _show_quiz(self) -> None:
        if not self.session:
            return
        rel_ms = self._pygame.mixer.music.get_pos() if self._pygame else 0
        pos_ms = self._play_started_pos_ms + max(0, rel_ms)
        chunk_idx = self.session.chunk_index_at(pos_ms)
        chunk_text = self.session.chunk_text(chunk_idx)
        try:
            questions = self.quiz_provider.questions(chunk_text, n=3)
        except NotImplementedError:
            self.status_var.set("Quiz provider not implemented yet — see quiz.py TODO(human).")
            return
        win = tk.Toplevel(self.root)
        win.title(f"Quiz — chunk {chunk_idx + 1}")
        for i, q in enumerate(questions, 1):
            ttk.Label(win, text=f"{i}. {q.text}", wraplength=520, justify=tk.LEFT).pack(anchor="w", padx=12, pady=4)

    def _save_session(self) -> None:
        if not self.session:
            return
        rel_ms = self._pygame.mixer.music.get_pos() if self._pygame else 0
        pos_ms = max(0, self._play_started_pos_ms + (rel_ms if rel_ms >= 0 else 0))
        chunks_done = self.session.chunk_index_at(pos_ms) + 1
        record = session_log.SessionRecord.now(
            text_hash=_text_hash(self.text, self.language, self.rate),
            voice=self.language,
            word_count=len(self.session.events),
            duration_ms=self.session.total_duration_ms,
            chunks_done=chunks_done,
        )
        path = session_log.append(record)
        self.status_var.set(f"Saved to {path}")


def launch(
    text: str,
    language: str = "en",
    rate: str = "+0%",
    chunk_size_words: int = 200,
    quiz_provider: Optional[QuizProvider] = None,
) -> None:
    """Entry point used by ``main.py --study``."""
    StudyPlayer(
        text=text,
        language=language,
        rate=rate,
        chunk_size_words=chunk_size_words,
        quiz_provider=quiz_provider,
    ).launch()
