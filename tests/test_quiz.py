"""Tests for quiz — QuizProvider Protocol surface + RuleBasedProvider plumbing.

The actual rule-based generation is a TODO(human), so we only test the
surrounding contract: empty-input guard, n cap, Protocol conformance, and
that the unimplemented slot raises clearly when reached.
"""

import pytest

from TTS_ka.quiz import (
    LLMQuizProvider,
    Question,
    QuizProvider,
    RuleBasedProvider,
)


class _StubProvider:
    """Minimal in-test provider used to verify Protocol conformance."""

    def questions(self, chunk_text: str, n: int = 3):
        return [Question(text=f"q{i}") for i in range(n)]


class TestQuestion:
    def test_default_fields(self):
        q = Question(text="Why?")
        assert q.expected_keywords == []
        assert q.kind == "open"

    def test_frozen(self):
        q = Question(text="Why?")
        with pytest.raises(Exception):
            q.text = "no"  # type: ignore[misc]


class TestQuizProviderProtocol:
    def test_runtime_isinstance_check(self):
        # Protocol is @runtime_checkable, so isinstance must work.
        assert isinstance(_StubProvider(), QuizProvider)

    def test_rule_based_satisfies_protocol(self):
        assert isinstance(RuleBasedProvider(), QuizProvider)


class TestRuleBasedProvider:
    def test_empty_chunk_returns_empty(self):
        assert RuleBasedProvider().questions("") == []
        assert RuleBasedProvider().questions("   \n\t  ") == []

    def test_zero_or_negative_n_returns_empty(self):
        # Non-empty text but n<=0 → caller asked for no questions.
        assert RuleBasedProvider().questions("real text", n=0) == []
        assert RuleBasedProvider().questions("real text", n=-3) == []

    def test_calls_into_todo_slot(self):
        # Until the TODO(human) is filled, non-empty input must surface the
        # NotImplementedError so the player can react instead of returning
        # silently misleading empty results.
        with pytest.raises(NotImplementedError):
            RuleBasedProvider().questions("Some chapter text here.")


class TestLLMQuizProviderStub:
    def test_stub_refuses_to_construct(self):
        with pytest.raises(NotImplementedError):
            LLMQuizProvider()
