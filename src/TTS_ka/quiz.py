"""Comprehension-check generator for study-mode chunks.

The design intent is *one swappable Protocol*: ``QuizProvider``. The default
implementation, :class:`RuleBasedProvider`, has no external dependencies and
produces simple retention questions from plain text. Cloud or local LLM
providers can be added later without touching the player or session state —
they only need to satisfy the :class:`QuizProvider` interface.

A :class:`Question` is intentionally generic — it carries the prompt and an
optional list of expected keywords that callers can use for naive
self-grading (keyword overlap) or simply display alongside a "did you get
it?" yes/no toggle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Protocol, runtime_checkable


@dataclass(frozen=True)
class Question:
    """A single retention prompt for a chunk of text."""

    text: str
    expected_keywords: List[str] = field(default_factory=list)
    kind: str = "open"  # "open" | "fill-blank" | "factual" | "summary"


@runtime_checkable
class QuizProvider(Protocol):
    """Anything that can turn a chunk of text into retention questions."""

    def questions(self, chunk_text: str, n: int = 3) -> List[Question]:
        ...


class RuleBasedProvider:
    """Zero-dependency provider that generates questions via simple rules.

    The actual question-generation strategy is intentionally left to the
    project owner — see ``_generate_for_chunk`` below. This class handles
    the surrounding plumbing (empty-input guard, n-question cap, public
    Protocol surface) so that any rule design plugs in cleanly.
    """

    def questions(self, chunk_text: str, n: int = 3) -> List[Question]:
        text = (chunk_text or "").strip()
        if not text:
            return []
        if n <= 0:
            return []
        generated = self._generate_for_chunk(text)
        return generated[:n]

    def _generate_for_chunk(self, chunk_text: str) -> List[Question]:
        # TODO(human): implement the rule-based question-generation strategy.
        #
        # Inputs:
        #   chunk_text — a stripped, non-empty string (typically ~200 words
        #   of narrative prose).
        #
        # Output:
        #   A list of Question objects. The public .questions() wrapper
        #   will cap this at the caller's requested `n`, so generating
        #   slightly more than needed is fine.
        #
        # Design space to consider (pick a lane and document it):
        #   1) Fill-in-the-blank: pick "important" tokens (longest words,
        #      capitalized non-sentence-start words, named entities found
        #      by regex on Title Case patterns), and produce
        #      "Original sentence with ____ replacing the picked token".
        #      Kind: "fill-blank". Expected keywords: [the blanked token].
        #
        #   2) Who/What/When template: scan for proper nouns and numbers,
        #      construct "Who is X?" / "What happened at Y?" prompts.
        #      Kind: "factual". Expected keywords: surrounding context words.
        #
        #   3) Summary prompt: a single open question like
        #      "In 1-2 sentences, what happened in this chunk?" plus 1-2
        #      anchor keywords pulled from the chunk to self-grade against.
        #      Kind: "summary". Expected keywords: top-frequency content
        #      words after stopword removal.
        #
        # Honest trade-off: rule-based questions are stupid by LLM standards
        # but they ARE good enough to answer "did I actually read this?",
        # which is the only metric the session log needs. Don't over-engineer.
        raise NotImplementedError(
            "RuleBasedProvider._generate_for_chunk is the TODO(human) slot."
        )


class LLMQuizProvider:
    """Placeholder for a future cloud/local LLM provider.

    Implement by satisfying the :class:`QuizProvider` Protocol —
    typically: prompt the model with the chunk + a system instruction
    requesting N retention questions in JSON, parse, return.
    """

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError(
            "LLMQuizProvider is a stub. Pick a backend (Anthropic, OpenAI, "
            "Ollama) and implement .questions() against the QuizProvider Protocol."
        )

    def questions(self, chunk_text: str, n: int = 3) -> List[Question]:
        raise NotImplementedError
