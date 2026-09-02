"""Deterministic 'count objects -> match the set of counters' DI packet.

Kindergarten counting topics (e.g. MA.K.NSO.1.1 / MA.K.NSO.2.1 — count a set and
match it to a quantity) are fully algorithmic: show N objects, offer four
five-frames with different amounts of red counters, and the student picks the one
whose count matches. We therefore BUILD this packet in code instead of asking the
LLM to invent it — that guarantees the numbers stay in range, the visuals are
always correct, the answer key is exact, and it costs zero AI tokens.

The output re-uses the same tier envelope as ai.generate_di_packets (tier / stars
/ band / tlc_sessions / days / opm) so the rest of the pipeline — student
grouping, HTML/PDF export — works unchanged. Each DAY carries the template a
teacher approved:  I DO -> WE DO -> CHECK FOR UNDERSTANDING -> YOU DO (4) ->
EXIT SLIP, and Red/Yellow get a 10-item OPM after Day 2.
"""
from __future__ import annotations

import random

# Generic, friendly object bank (kept theme-neutral per the teacher's request —
# not only beach objects). Each key has an SVG glyph in export_html._glyph().
OBJECTS = [
    "suns", "stars", "apples", "fish", "flowers",
    "balloons", "sailboats", "butterflies", "beach balls", "turtles",
]

# The five per-day blocks, in order, with how many items each holds.
_SECTIONS = [
    ("i_do", "I DO — Teacher Models",
     "Touch each object once, count aloud, say the total, then check the counters."),
    ("we_do", "WE DO — Guided Practice",
     "Complete together. Ask: Which counter set has the same amount?"),
    ("cfu", "CHECK FOR UNDERSTANDING",
     "Student answers with minimal prompting."),
    ("you_do", "YOU DO — Work independently",
     "Each question and all answer choices stay together."),
    ("exit", "EXIT SLIP", "One quick check before you finish."),
]
_SECTION_COUNT = {"i_do": 1, "we_do": 1, "cfu": 1, "you_do": 4, "exit": 1}

_LETTERS = ["A", "B", "C", "D"]


def _one_item(rng: random.Random, ceiling: int) -> dict:
    """One count-and-match question: an object, its true count, and four
    five-frame choices (0..ceiling) with exactly one correct."""
    ceiling = max(1, min(10, ceiling))
    count = rng.randint(1, ceiling)
    # Three distinct distractors in range, never equal to the true count.
    pool = [v for v in range(0, ceiling + 1) if v != count]
    rng.shuffle(pool)
    choices = [count] + pool[:3]
    # If the range is tiny (ceiling < 3) we may not have 3 distractors; pad by
    # allowing values up to 5 so there are always four options.
    extra = [v for v in range(0, 6) if v != count and v not in choices]
    while len(choices) < 4 and extra:
        choices.append(extra.pop(0))
    choices = choices[:4]
    rng.shuffle(choices)
    answer = _LETTERS[choices.index(count)]
    obj = rng.choice(OBJECTS)
    return {"objects": obj, "count": count, "choices": choices, "answer": answer}


def _day(rng: random.Random, day_no: int, ceiling: int) -> dict:
    sections = {}
    for key, _title, _note in _SECTIONS:
        n = _SECTION_COUNT[key]
        sections[key] = [_one_item(rng, ceiling) for _ in range(n)]
    return {"day": day_no, "title": "Count and match the set of counters",
            "pacing": "I do 5 min · We do 5 min · You do 15 min · Exit 5 min",
            "sections": sections}


def build_count_match_packet(standard: dict, grade: str, tiers: list,
                             number_max: int | None = None) -> dict:
    """Build the full three-tier count-match packet deterministically.

    tiers is _DI_ROTATION (Intensive/Cusp/Strategic with tlc_sessions). ceiling is
    the biggest number to count to (default 5 for Kinder Topic 1)."""
    code = standard.get("code", "")
    ceiling = number_max if (number_max and number_max > 0) else 5
    ceiling = max(1, min(10, ceiling))

    out_tiers = []
    for t in tiers:
        # Seed per tier+standard so a regenerate is reproducible but each tier and
        # day still has its own fresh set of objects and amounts.
        rng = random.Random(f"{code}|{t['name']}|{ceiling}")
        days = [_day(rng, d + 1, ceiling) for d in range(t.get("tlc_sessions", 1))]
        # OPM (10 items) after Day 2 for the two lower groups, like the sample.
        opm = ([_one_item(rng, ceiling) for _ in range(10)]
               if t["name"] in ("Intensive", "Cusp") else [])
        out_tiers.append({
            "tier": t["name"], "stars": t["stars"], "band": t["band"],
            "tlc_sessions": t["tlc_sessions"], "days": days, "opm": opm,
        })

    return {
        "standard": code,
        "description": standard.get("description", ""),
        "grade_level": grade,
        "model": "five_frame",
        "format": "count_match",
        "target": "Count objects and match the quantity to a set of counters.",
        "vocab": [
            ("count", "tell how many"), ("set", "a group"),
            ("counter", "a dot that shows how many"), ("zero", "none"),
        ],
        "number_max": ceiling,
        "tiers": out_tiers,
        "ai_generated": False,
        "generated_by": "deterministic",
    }


def is_count_match_standard(code: str, description: str, grade: str) -> bool:
    """True when this K/PK benchmark is a 'count a set / match the quantity' skill,
    so we build the deterministic count-match packet instead of an AI one."""
    if (grade or "").upper() not in ("K", "PK"):
        return False
    text = f"{code} {description}".lower()
    keys = ("count", "quantit", "how many", "number of objects", "represent",
            "cardinal")
    return any(k in text for k in keys)
