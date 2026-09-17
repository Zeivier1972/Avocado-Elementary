"""Deterministic Kindergarten number-sense DI packets (no AI).

The Kinder number-sense test uses a handful of picture-based question TYPES, all
fully algorithmic, so we BUILD the packets in code — the numbers always stay in
range, the visuals are always correct, the answer key is exact, and it costs zero
AI tokens. Question types (each mirrors a real test item the teacher shared):

  * count_counters — "Count the ___. Which SET OF COUNTERS shows how many?"
                     (objects to count; four five-frame choices)
  * count_numeral  — "How many ___ are there?"  (objects to count; four numeral
                     choices, like the frog item)
  * number_order   — "Choose the numbers in ___ order. Start with ___."
                     (order/sequence; two number-string choices)

Which types a packet uses is DATA-DRIVEN: chosen from the benchmark being
retaught (its code + description), so an ordering standard gets ordering items
and a counting standard gets counting items — matching what the class missed.

Output re-uses ai.generate_di_packets' tier envelope (tier / stars / band /
tlc_sessions / days / opm) so student grouping and HTML/PDF export work
unchanged. Each DAY carries the approved template: I DO -> WE DO -> CHECK FOR
UNDERSTANDING -> YOU DO (4) -> EXIT SLIP; Red/Yellow get a 10-item OPM after
Day 2.
"""
from __future__ import annotations

import random

# Generic, friendly object bank (theme-neutral per the teacher's request). Each
# key has an SVG glyph in export_html._glyph().
OBJECTS = [
    "suns", "stars", "apples", "fish", "flowers",
    "balloons", "sailboats", "butterflies", "beach balls", "turtles", "frogs",
]

_LETTERS = ["A", "B", "C", "D"]

# The five per-day blocks, in order, with how many items each holds.
_SECTIONS = [
    ("i_do", "I DO — Teacher Models",
     "Touch each object once, count aloud, say the total, then check your answer."),
    ("we_do", "WE DO — Guided Practice",
     "Complete together. Ask: How do we know the amount matches?"),
    ("cfu", "CHECK FOR UNDERSTANDING", "Student answers with minimal prompting."),
    ("you_do", "YOU DO — Work independently",
     "Each question and all answer choices stay together."),
    ("exit", "EXIT SLIP", "One quick check before you finish."),
]
_SECTION_COUNT = {"i_do": 1, "we_do": 1, "cfu": 1, "you_do": 4, "exit": 1}


# --- Individual question-type builders ---------------------------------------
def _four_distinct(rng: random.Random, correct: int, ceiling: int) -> tuple:
    """A shuffled set of four distinct amounts including `correct`, and the letter
    that lands on the correct one."""
    pool = [v for v in range(0, ceiling + 1) if v != correct]
    rng.shuffle(pool)
    choices = [correct] + pool[:3]
    extra = [v for v in range(0, 6) if v != correct and v not in choices]
    while len(choices) < 4 and extra:
        choices.append(extra.pop(0))
    choices = choices[:4]
    rng.shuffle(choices)
    return choices, _LETTERS[choices.index(correct)]


def _count_counters_item(rng: random.Random, ceiling: int) -> dict:
    """Count the objects; pick the five-frame with the matching number of dots."""
    count = rng.randint(1, ceiling)
    choices, answer = _four_distinct(rng, count, ceiling)
    return {"type": "count_counters", "objects": rng.choice(OBJECTS),
            "count": count, "choices": choices, "answer": answer}


def _count_numeral_item(rng: random.Random, ceiling: int) -> dict:
    """Count the objects; pick the NUMERAL (like the frog item)."""
    count = rng.randint(1, ceiling)
    choices, answer = _four_distinct(rng, count, ceiling)
    return {"type": "count_numeral", "objects": rng.choice(OBJECTS),
            "count": count, "choices": choices, "answer": answer}


def _number_order_item(rng: random.Random, ceiling: int) -> dict:
    """Put numbers in order. Start number + direction; two number-string choices,
    one correct (in order), one scrambled — mirrors the 'reverse order' item."""
    length = max(3, min(5, ceiling))
    seq = list(range(1, length + 1))
    reverse = rng.random() < 0.5
    correct = seq[::-1] if reverse else seq[:]
    # A near-miss distractor: swap two positions so it's clearly out of order.
    wrong = correct[:]
    i = rng.randint(0, length - 2)
    wrong[i], wrong[i + 1] = wrong[i + 1], wrong[i]
    if wrong == correct:  # guard (shouldn't happen for length>=2)
        wrong[0], wrong[-1] = wrong[-1], wrong[0]
    opts = [correct, wrong]
    rng.shuffle(opts)
    answer = _LETTERS[opts.index(correct)]
    start = correct[0]
    word = "reverse" if reverse else "counting"
    return {"type": "number_order",
            "prompt": f"Choose the numbers in {word} order. Start with number {start}.",
            "sequences": [[str(n) for n in o] for o in opts], "answer": answer}


# type key -> builder
_BUILDERS = {
    "count_counters": _count_counters_item,
    "count_numeral": _count_numeral_item,
    "number_order": _number_order_item,
}


def _templates_for(code: str, description: str) -> tuple:
    """Data-driven: pick the question TYPES that assess this benchmark.

    Returns (primary, pool). `primary` is the type used for the worked I DO/WE DO
    model; `pool` is every applicable type, mixed through the rest of the packet."""
    text = f"{code} {description}".lower()
    # Strong ordering signals — these standards are ABOUT sequence, so lead with
    # the ordering model even when the word 'count' also appears.
    strong_order = ("order", "sequence", "forward", "backward", "reverse",
                    "before", "after", "next")
    count_kw = ("count", "how many", "quantit", "number of", "represent",
                "cardinal", "match", "set")
    is_order = any(k in text for k in strong_order)
    is_count = any(k in text for k in count_kw)
    if is_order and is_count:          # spans both — order first, then counting
        return "number_order", ["number_order", "count_counters", "count_numeral"]
    if is_order:
        return "number_order", ["number_order"]
    return "count_counters", ["count_counters", "count_numeral"]


def _item(rng: random.Random, ceiling: int, type_key: str) -> dict:
    return _BUILDERS[type_key](rng, ceiling)


def _day(rng: random.Random, day_no: int, ceiling: int,
         primary: str, pool: list) -> dict:
    sections = {}
    for key, _title, _note in _SECTIONS:
        n = _SECTION_COUNT[key]
        items = []
        for i in range(n):
            # Teach with the primary model; mix the applicable types elsewhere so
            # the packet looks like the real test (which rotates formats).
            if key in ("i_do", "we_do"):
                tk = primary
            else:
                tk = pool[(day_no + i) % len(pool)]
            items.append(_item(rng, ceiling, tk))
        sections[key] = items
    return {"day": day_no, "title": "Count, match, and order numbers",
            "pacing": "I do 5 min · We do 5 min · You do 15 min · Exit 5 min",
            "sections": sections}


def build_count_match_packet(standard: dict, grade: str, tiers: list,
                             number_max: int | None = None) -> dict:
    """Build the full three-tier Kinder number-sense packet deterministically.

    tiers is _DI_ROTATION (Intensive/Cusp/Strategic with tlc_sessions). ceiling is
    the biggest number to use (default 5 for Kinder Topic 1)."""
    code = standard.get("code", "")
    desc = standard.get("description", "")
    ceiling = number_max if (number_max and number_max > 0) else 5
    ceiling = max(1, min(10, ceiling))
    primary, pool = _templates_for(code, desc)

    out_tiers = []
    for t in tiers:
        # Seed per tier+standard so a regenerate is reproducible, yet each tier and
        # day still gets its own fresh objects and amounts.
        rng = random.Random(f"{code}|{t['name']}|{ceiling}")
        days = [_day(rng, d + 1, ceiling, primary, pool)
                for d in range(t.get("tlc_sessions", 1))]
        opm = ([_item(rng, ceiling, pool[i % len(pool)]) for i in range(10)]
               if t["name"] in ("Intensive", "Cusp") else [])
        out_tiers.append({
            "tier": t["name"], "stars": t["stars"], "band": t["band"],
            "tlc_sessions": t["tlc_sessions"], "days": days, "opm": opm,
        })

    return {
        "standard": code,
        "description": desc,
        "grade_level": grade,
        "model": "five_frame",
        "format": "count_match",
        "target": desc or "Count objects, match the quantity, and order numbers.",
        "vocab": [
            ("count", "tell how many"), ("set", "a group"),
            ("counter", "a dot that shows how many"),
            ("order", "put in a row: 1, 2, 3…"), ("zero", "none"),
        ],
        "number_max": ceiling,
        "tiers": out_tiers,
        "ai_generated": False,
        "generated_by": "deterministic",
    }


def is_count_match_standard(code: str, description: str, grade: str) -> bool:
    """True when this K/PK benchmark is a number-sense skill we build
    deterministically (count a set, match a quantity, or order numbers)."""
    if (grade or "").upper() not in ("K", "PK"):
        return False
    text = f"{code} {description}".lower()
    keys = ("count", "quantit", "how many", "number of objects", "represent",
            "cardinal", "order", "sequence", "forward", "backward", "match",
            "before", "after")
    return any(k in text for k in keys)
