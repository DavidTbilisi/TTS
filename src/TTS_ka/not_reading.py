"""Filters for non-readable substrings.

Provides helpers to replace code blocks, inline code, links, and very
large numeric sequences with short, readable placeholders so TTS engines
don't attempt to speak raw code/URLs/huge numbers.
"""

from __future__ import annotations

import re
from typing import Pattern

__all__ = [
	"replace_not_readable",
	"filter_code_blocks",
	"filter_inline_code",
	"filter_urls",
	"filter_big_numbers",
]


CODE_BLOCK_RE: Pattern = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE: Pattern = re.compile(r"`([^`]+)`")
URL_RE: Pattern = re.compile(r"\b(?:https?://|http://|www\.)\S+\b", re.IGNORECASE)
BIG_NUMBER_RE: Pattern = re.compile(r"\b\d{7,}\b")  # 7+ digits => >= 1,000,000


def filter_code_blocks(text: str) -> str:
	"""Replace fenced code blocks (```...```) with a placeholder."""
	return CODE_BLOCK_RE.sub(" you can see code in text ", text)


def filter_inline_code(text: str) -> str:
	"""Replace inline backtick code spans with a placeholder."""
	return INLINE_CODE_RE.sub(" you can see code in text ", text)


def filter_urls(text: str) -> str:
	"""Replace URLs and www links with a placeholder."""
	return URL_RE.sub(" see link in text ", text)


def filter_big_numbers(text: str) -> str:
	"""Replace long digit sequences (7+ digits) with a placeholder.

	This treats any contiguous run of 7 or more digits as a "big number"
	(i.e., >= 1,000,000) which is usually not useful to speak verbatim.
	"""
	return BIG_NUMBER_RE.sub(" a large number ", text)


def replace_not_readable(text: str) -> str:
	"""Apply all filters and return a cleaned string suitable for TTS.

	Filters are applied in an order that avoids accidental re-matching:
	1. Code blocks
	2. Inline code
	3. URLs
	4. Big numbers

	The result is whitespace-normalized.
	"""
	if not text:
		return text

	s = text
	s = filter_code_blocks(s)
	s = filter_inline_code(s)
	s = filter_urls(s)
	s = filter_big_numbers(s)

	# Normalize whitespace created by replacements
	s = re.sub(r"\s{2,}", " ", s).strip()
	return s


if __name__ == "__main__":
	# Quick manual check when run as script
	sample = (
		"Here is code: ```def f(): pass``` and inline `x=1` and a link https://example.com "
		"and a big number 12345678."
	)
	print(replace_not_readable(sample))