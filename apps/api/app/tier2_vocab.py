"""Tier 2 academic vocabulary — the cross-curricular words (determine, explain,
justify …) that show up in the QUESTION STEMS of standards across every subject.
This is the school's focus this year, so we mine each grade's standards for these
words and feed them into the planning guide and the lesson-plan template.

Tier 2 = academic, used in ANY subject. Tier 3 = domain/subject-specific (array,
quotient) — handled separately in app.ai.
"""
from __future__ import annotations

import re

# Curated Tier 2 academic word bank with kid-friendly meanings. These are the
# high-utility academic words that carry meaning in a test question regardless of
# subject. Keyed by base form; matching also catches common endings (-s/-ed/-ing).
TIER2_MEANINGS: dict[str, str] = {
    "determine": "figure out",
    "explain": "tell how or why",
    "justify": "give reasons that prove it",
    "describe": "tell about it with details",
    "compare": "tell how things are alike or different",
    "contrast": "tell how things are different",
    "represent": "show it another way — a picture, model, or number",
    "identify": "point out or name",
    "interpret": "figure out what it means",
    "analyze": "break it apart to understand it",
    "evaluate": "find the value or judge it",
    "estimate": "make a smart, close guess",
    "solve": "find the answer",
    "demonstrate": "show how",
    "apply": "use what you know",
    "illustrate": "show it with a picture or example",
    "classify": "sort into groups",
    "distinguish": "tell the difference",
    "generalize": "make a rule that always works",
    "infer": "figure it out from clues",
    "predict": "say what will happen",
    "summarize": "tell the main idea in a few words",
    "construct": "build or make it",
    "develop": "build it up step by step",
    "relate": "connect ideas or show how they go together",
    "model": "show it with objects, pictures, or numbers",
    "decompose": "break a number apart into parts",
    "compose": "put parts together to make a whole",
    "recognize": "know it when you see it",
    "select": "choose",
    "combine": "put together",
    "express": "write or say it another way",
    "verify": "check that it is true",
    "reasonable": "makes sense",
    "relationship": "how two things are connected",
    "pattern": "something that repeats in a rule",
    "strategy": "a plan or way to solve it",
    "value": "how much something is worth",
    "quantity": "how much or how many",
    "unknown": "the missing amount you are solving for",
    "represents": "shows",  # safety: also matched by 'represent'
    "equal": "the same amount as",
    "estimate.": "",  # guard (never used)
}
# Drop guard/dup helper keys that aren't real bases.
for _k in ("represents", "estimate."):
    TIER2_MEANINGS.pop(_k, None)

# One regex that finds any base form plus common inflections as whole words.
_TIER2_RE = re.compile(
    r"\b(" + "|".join(sorted(TIER2_MEANINGS, key=len, reverse=True)) + r")(s|es|d|ed|ing)?\b",
    re.I,
)


def _standard_text(s: dict) -> str:
    """All the readable B1G-M text for a standard where Tier 2 words live."""
    parts = [s.get("description", "")]
    parts += s.get("clarifications", []) or []
    a = s.get("alds") or {}
    parts += [str(a.get(k, "")) for k in ("level2", "level3", "level4", "level5")]
    parts.append(str(s.get("strategies", "")))
    return " ".join(p for p in parts if p)


def tier2_for_standards(standards: list[dict]) -> list[dict]:
    """Mine Tier 2 academic words from a set of standards. Returns
    [{word, meaning, standards:[codes], count}] sorted by how often they appear
    (most common academic demand first)."""
    hits: dict[str, dict] = {}
    for s in standards:
        code = s.get("code", "")
        for m in _TIER2_RE.finditer(_standard_text(s)):
            base = m.group(1).lower()
            if base not in TIER2_MEANINGS:
                continue
            e = hits.setdefault(base, {"word": base, "meaning": TIER2_MEANINGS[base],
                                       "standards": [], "count": 0})
            e["count"] += 1
            if code and code not in e["standards"]:
                e["standards"].append(code)
    out = sorted(hits.values(), key=lambda x: (-x["count"], x["word"]))
    return out


def tier2_words(standards: list[dict]) -> list[str]:
    """Just the ordered list of Tier 2 words for these standards."""
    return [e["word"] for e in tier2_for_standards(standards)]
