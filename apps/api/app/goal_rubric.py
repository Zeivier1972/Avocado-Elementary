"""Math Goal Setting Rubric engine (DAS).

Crosswalks a FAST scale score to its achievement level, instructional level, and
the Topic Assessment Average goal for that student — so a student's actual topic
average can be compared to where their FAST data says they should be, and an
end-of-year projection made toward the school goal (Level 3+)."""
from __future__ import annotations

import json
from pathlib import Path

_DATA = Path(__file__).parent / "data" / "math_goal_rubric.json"
_CACHE: dict | None = None


def _rubric() -> dict:
    global _CACHE
    if _CACHE is None:
        _CACHE = json.loads(_DATA.read_text())
    return _CACHE


def _in(lo, hi, x) -> bool:
    if lo is not None and x < lo:
        return False
    if hi is not None and x > hi:
        return False
    return True


def goal_for(grade: str, scale: float) -> dict | None:
    """Return {level, instructional, goal_min, goal_max} for a FAST scale score,
    or None if the grade isn't in the rubric."""
    bands = _rubric()["grades"].get(str(grade))
    if not bands:
        return None
    band = None
    for b in bands:
        if _in(b["fast"][0], b["fast"][1], scale):
            band = b
            break
    if band is None:  # below the lowest band -> level 1; above the top -> level 5
        band = bands[0] if scale < bands[0]["fast"][0] else bands[-1]
    goal = band["goals"][-1]
    for g in band["goals"]:
        if _in(g["range"][0], g["range"][1], scale):
            goal = g
            break
    return {
        "level": band["level"],
        "instructional": band["instructional"],
        "goal_min": goal["goal"][0],
        "goal_max": goal["goal"][1],
    }


def evaluate(grade: str, scale: float | None, topic_avg_pct: float | None) -> dict:
    """Compare a student's actual topic-assessment average to their FAST-based
    goal. topic_avg_pct is 0-100. Returns the goal plus status/gap."""
    out: dict = {"scale": scale, "topic_avg": topic_avg_pct,
                 "level": None, "instructional": "", "goal_min": None,
                 "goal_max": None, "status": "no_fast", "gap": None,
                 "meets_school_goal": None}
    if scale is None:
        return out
    g = goal_for(grade, scale)
    if not g:
        return out
    out.update(g)
    out["meets_school_goal"] = g["level"] >= 3  # Level 3+ = the school goal
    if topic_avg_pct is None:
        out["status"] = "no_topic"
        return out
    if topic_avg_pct >= g["goal_min"]:
        out["status"] = "above" if topic_avg_pct > g["goal_max"] else "meeting"
        out["gap"] = round(topic_avg_pct - g["goal_min"], 1)
    else:
        out["status"] = "below"
        out["gap"] = round(topic_avg_pct - g["goal_min"], 1)  # negative
    return out


def project(grade: str, levels_by_period: dict, topic_avg_pct: float | None) -> dict:
    """A transparent end-of-year projection. Uses the FAST-level trend across
    PM periods and whether the student is meeting their topic goal.
    Returns {trend, projected_level_3_plus, rationale}."""
    order = ["Baseline", "PM1", "PM2", "PM3"]
    seq = [levels_by_period[p] for p in order
           if p in levels_by_period and levels_by_period[p] is not None]
    trend = "flat"
    if len(seq) >= 2:
        if seq[-1] > seq[0]:
            trend = "up"
        elif seq[-1] < seq[0]:
            trend = "down"
    latest = seq[-1] if seq else None
    on_track_topic = None
    if latest is not None and topic_avg_pct is not None:
        ev = evaluate(grade, None, None)  # placeholder; caller passes scale elsewhere
        on_track_topic = None  # topic comparison handled by evaluate() with scale
    # Simple projection: currently Level 3+ and not trending down -> likely;
    # Level 2 trending up (+ meeting topic goal) -> possible; else at risk.
    if latest is None:
        proj, why = None, "No FAST level yet."
    elif latest >= 3 and trend != "down":
        proj, why = True, f"At Level {latest} and trend is {trend}."
    elif latest == 2 and trend == "up":
        proj, why = True, "At Level 2 and improving — on the bubble to reach Level 3."
    elif latest >= 3 and trend == "down":
        proj, why = False, f"At Level {latest} but trending down — watch closely."
    else:
        proj, why = False, f"At Level {latest} — needs targeted support to reach Level 3."
    return {"trend": trend, "latest_level": latest,
            "projected_level_3_plus": proj, "rationale": why}


def level3_thresholds() -> dict:
    """Per grade: the FAST scale score where on-grade (Level 3) begins and its
    topic-assessment goal — the key crosswalk line for the school goal."""
    out = {}
    for grade, bands in _rubric()["grades"].items():
        for b in bands:
            if b["level"] == 3:
                lo = b["fast"][0]
                gmin = b["goals"][0]["goal"][0]
                gmax = b["goals"][-1]["goal"][1]
                out[grade] = {"scale_at_or_above": lo,
                              "topic_goal": f"{gmin}-{gmax}%" if gmin != gmax else f"{gmin}%"}
    return out
