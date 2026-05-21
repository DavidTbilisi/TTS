"""Parse, validate, and serialize SSML prosody attributes (rate/pitch/volume).

The CLI surface accepts free-form strings like ``+30%``, ``-2Hz``, etc.; this
module converts them into edge-tts / Azure-compatible values, clamping
out-of-range inputs with a stderr warning. Invalid inputs raise SystemExit(2).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Optional, Tuple

# Safe maxima — beyond these the audio is unintelligible.
RATE_MIN, RATE_MAX = -50, 200   # % relative to default
PITCH_HZ_MIN, PITCH_HZ_MAX = -100, 100
PITCH_PCT_MIN, PITCH_PCT_MAX = -50, 50
VOLUME_MIN, VOLUME_MAX = -100, 100

_PCT_RE = re.compile(r"^([+-])(\d+)%$")
_HZ_RE = re.compile(r"^([+-])(\d+)Hz$")


@dataclass(frozen=True)
class ProsodyOpts:
    """Resolved, edge-tts compatible prosody triplet."""
    rate: str = "+0%"
    pitch: str = "+0Hz"
    volume: str = "+0%"

    def is_default(self) -> bool:
        return self == ProsodyOpts()


def _parse_signed(raw: str, pattern: re.Pattern, label: str) -> Tuple[int, str]:
    """Match *raw* against *pattern*, returning (signed_int, unit_str).

    Raises SystemExit(2) on invalid syntax.
    """
    m = pattern.match(raw.strip())
    if not m:
        print(
            f"Error: invalid --{label} value {raw!r}. "
            f"Expected a signed value like '+30%' (rate/volume) or '+5Hz' (pitch).",
            file=sys.stderr,
        )
        raise SystemExit(2)
    sign, magnitude = m.group(1), m.group(2)
    value = int(magnitude) * (1 if sign == "+" else -1)
    return value, sign


def _clamp(value: int, lo: int, hi: int, label: str, raw: str) -> int:
    if value < lo or value > hi:
        clamped = max(lo, min(hi, value))
        print(
            f"Warning: --{label} {raw!r} out of range [{lo}, {hi}]; clamped to {clamped:+d}.",
            file=sys.stderr,
        )
        return clamped
    return value


def parse_rate(raw: Optional[str]) -> str:
    """Normalize a --rate value to '+N%' edge-tts form."""
    if raw is None:
        return "+0%"
    value, _ = _parse_signed(raw, _PCT_RE, "rate")
    value = _clamp(value, RATE_MIN, RATE_MAX, "rate", raw)
    return f"{value:+d}%"


def parse_pitch(raw: Optional[str]) -> str:
    """Normalize a --pitch value to '+NHz' edge-tts form. Accepts Hz or %."""
    if raw is None:
        return "+0Hz"
    raw = raw.strip()
    if _HZ_RE.match(raw):
        value, _ = _parse_signed(raw, _HZ_RE, "pitch")
        value = _clamp(value, PITCH_HZ_MIN, PITCH_HZ_MAX, "pitch", raw)
        return f"{value:+d}Hz"
    if _PCT_RE.match(raw):
        # Convert % to a fake Hz figure (rough approximation: 1% ~= 1Hz)
        value, _ = _parse_signed(raw, _PCT_RE, "pitch")
        value = _clamp(value, PITCH_PCT_MIN, PITCH_PCT_MAX, "pitch", raw)
        return f"{value:+d}Hz"
    print(
        f"Error: invalid --pitch value {raw!r}. Expected '+5Hz', '-10Hz', '+10%', etc.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def parse_volume(raw: Optional[str]) -> str:
    """Normalize a --volume value to '+N%' edge-tts form."""
    if raw is None:
        return "+0%"
    value, _ = _parse_signed(raw, _PCT_RE, "volume")
    value = _clamp(value, VOLUME_MIN, VOLUME_MAX, "volume", raw)
    return f"{value:+d}%"


def build_opts(rate: Optional[str], pitch: Optional[str],
               volume: Optional[str]) -> ProsodyOpts:
    """Resolve raw CLI values into a validated ProsodyOpts."""
    return ProsodyOpts(
        rate=parse_rate(rate),
        pitch=parse_pitch(pitch),
        volume=parse_volume(volume),
    )


def to_ssml_attrs(opts: ProsodyOpts) -> str:
    """Render a ProsodyOpts as the attributes of an SSML <prosody> tag."""
    return f"rate='{opts.rate}' pitch='{opts.pitch}' volume='{opts.volume}'"
