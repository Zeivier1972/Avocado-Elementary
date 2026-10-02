"""i-Ready / STAR → FAST level concordance.

The district publishes alignment charts that map an i-Ready Math scale score
(grades 3-5) or a STAR Math scale score / "Unified" score (grades K-2) to a FAST
achievement level (1-5). This lets a mid-year i-Ready or STAR result stand on the
SAME 1-5 scale the app uses for FAST — feeding goals, color codes, and the school
goal (Level 3+) between PM windows.

MATH only (the charts are math). Thresholds live in data/fast_concordance.json so
they can be corrected without a code change.
"""
from __future__ import annotations

import json
from pathlib import Path

_DATA = Path(__file__).parent / "data" / "fast_concordance.json"
_CACHE: dict | None = None


def _tables() -> dict:
    global _CACHE
    if _CACHE is None:
        _CACHE = json.loads(_DATA.read_text())
    return _CACHE


def _norm_grade(grade) -> str:
    g = str(grade or "").strip().upper()
    if g in ("00", "0", "KG"):
        return "K"
    return g.lstrip("0") or g  # "03" -> "3"


def to_fast_level(source: str, grade, subject, scale) -> int | None:
    """Return the FAST achievement level (1-5) for an i-Ready/STAR MATH scale
    score, or None when no concordance applies (wrong subject, unknown grade,
    unmapped source, or missing score)."""
    if scale is None:
        return None
    if str(subject or "").strip().upper() not in ("MATH", "MA", "M", ""):
        return None
    src = str(source or "").strip().upper()
    table = _tables().get(src)
    if not table:
        return None
    thresholds = table.get(_norm_grade(grade))
    if not thresholds:
        return None
    try:
        s = float(scale)
    except (TypeError, ValueError):
        return None
    level = 1
    for min_score, lv in thresholds:  # ascending; take the highest one met
        if s >= min_score:
            level = int(lv)
    return level


def has_grade(source: str, grade) -> bool:
    """Whether a concordance exists for this source+grade (e.g. i-Ready only
    covers 3-5, STAR only K-2)."""
    table = _tables().get(str(source or "").strip().upper()) or {}
    return _norm_grade(grade) in table
