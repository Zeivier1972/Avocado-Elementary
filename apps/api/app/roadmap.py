"""Deterministic parser for the M-DCPS Academic Instructional Roadmap (AIR).

The roadmap is a highly regular table — Section IV "Instructional Framework"
lays out one row per day with the day number, the real calendar date, and the
day's focus (a numbered lesson, the chapter prerequisite, the review, or the
topic assessment). Reading it with a few rules is far more reliable than asking
a model to recover it from flattened table text, and it captures the EXACT
dates the district assigned — which the pacing calendar should honor instead of
re-sequencing weekdays from a guessed start date.

parse_roadmap(text) returns the day-by-day schedule (with ISO dates) plus the
teaching-lesson list, or None when the text is not an AIR roadmap.
"""
from __future__ import annotations

import re

_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})\b")
_DAY = re.compile(r"^\s*Day\s+(\d{1,2})\s*$", re.M)
_LESSON = re.compile(r"\bLesson\s+(\d{1,2}\.\d{1,2})\b")
_STD = re.compile(r"MA\.[A-Z0-9]+\.[A-Z]+\.\d+\.\d+")


def _iso(m: re.Match) -> str:
    """A regex date match -> ISO 'YYYY-MM-DD' (2-digit years map to 2000-2099)."""
    mo, dy, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if yr < 100:
        yr += 2000
    try:
        from datetime import date
        return date(yr, mo, dy).isoformat()
    except ValueError:
        return ""


def _looks_like_roadmap(text: str) -> bool:
    t = text.lower()
    hits = sum(k in t for k in (
        "instructional roadmap", "instructional framework", "daily focus",
        "timeframe", "pacing window"))
    return hits >= 2 and bool(_DAY.search(text))


def _header(text: str) -> dict:
    """Grade, topic code/name and the pacing window from the roadmap header."""
    out = {"grade": "", "topic_code": "", "topic_name": "",
           "pacing_start": "", "pacing_end": ""}
    m = re.search(r"Grade\s*(K|[0-8])\b", text)
    if m:
        out["grade"] = m.group(1).upper()
    # "Unit / Topic Title:" ... "Topic 5: Subtract Numbers within 20"
    m = re.search(r"(Topic|Chapter)\s+(\d+)\s*:?\s*([^\n]*)", text)
    if m:
        out["topic_code"] = f"{m.group(1).title()} {m.group(2)}"
        name = (m.group(3) or "").strip()
        # The title often runs straight into the next cell's label — cut at the
        # first heading-ish word so we keep just the topic name.
        name = re.split(r"\s{2,}|Essential|Pacing|Assessment|Course", name)[0]
        out["topic_name"] = name.strip(": ").strip()
    # Pacing Window: "10/19/2026 – 10/30/2026"
    win = re.search(r"Pacing Window[^\n]*\n?\s*" + _DATE.pattern +
                    r"\s*[–—-]\s*" + _DATE.pattern, text)
    if win:
        a = _DATE.search(win.group(0))
        alld = _DATE.findall(win.group(0))
        if a:
            out["pacing_start"] = _iso(a)
        ends = list(_DATE.finditer(win.group(0)))
        if len(ends) >= 2:
            out["pacing_end"] = _iso(ends[1])
    return out


def _classify(block: str) -> tuple[str, str, str, list, str]:
    """From one day's text block return (kind, code, title, standards, objective).
    kind is lesson | prerequisite | review | assessment | other."""
    up = block.upper()
    standards = list(dict.fromkeys(_STD.findall(block)))
    obj = ""
    mo = re.search(r"Learning Objective/Target:\s*\n?\s*([^\n]+)", block)
    if mo:
        obj = mo.group(1).strip()
    ml = _LESSON.search(block)
    if ml:
        code = ml.group(1)
        # Title = the first non-empty line AFTER "Lesson X.Y" that isn't a
        # standards line or the objective label.
        tail = block[ml.end():]
        title = ""
        for ln in tail.splitlines():
            s = ln.strip()
            if not s:
                continue
            if _STD.search(s) or s.lower().startswith("learning objective"):
                break
            title = s
            break
        if not title and obj:
            title = obj
        return "lesson", code, title or f"Lesson {code}", standards, obj
    if "PREREQUISITE" in up:
        return "prerequisite", "", "Prerequisite / Launch the Chapter", standards, obj
    if "REVIEW" in up:
        return "review", "", "Topic Review", standards, obj
    if "ASSESSMENT" in up:
        return "assessment", "", "Topic Assessment", standards, obj
    return "other", "", "", standards, obj


def parse_roadmap(text: str) -> dict | None:
    """Parse an M-DCPS AIR roadmap into a dated day-by-day schedule.

    Returns {grade, topic_code, topic_name, pacing_start, pacing_end, days:[...]}
    where each day is {day, date, kind, code, title, benchmarks, focus}; or None
    when the text is not a recognizable roadmap or has no dated day rows.
    """
    if not text or not _looks_like_roadmap(text):
        return None
    head = _header(text)
    # Only the "Instructional Framework" table (Section IV) holds the dated day
    # rows. Bound the search to it so the LAST day's block doesn't run on into the
    # later sections (Differentiated Instruction, Enrichment, …) and pick up their
    # stray "prerequisite" / standards text.
    iv = re.search(r"Instructional Framework", text)
    nxt = re.search(r"\bV\.\s*Differentiated Instruction|\bDifferentiated "
                    r"Instruction\b", text[iv.end():]) if iv else None
    lo = iv.end() if iv else 0
    hi = (lo + nxt.start()) if nxt else len(text)
    body = text[lo:hi]
    # Split the body into per-day blocks on the "Day N" markers.
    marks = list(_DAY.finditer(body))
    if len(marks) < 2:
        return None
    days = []
    for i, m in enumerate(marks):
        day_no = int(m.group(1))
        start = m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        block = body[start:end]
        dm = _DATE.search(block)
        iso = _iso(dm) if dm else ""
        if not iso:
            continue  # a "Day N" with no date isn't a real schedule row
        kind, code, title, stds, obj = _classify(block)
        days.append({
            "day": day_no, "date": iso, "kind": kind, "code": code,
            "title": title, "benchmarks": stds, "focus": obj,
        })
    # De-duplicate by day number (a day's text can repeat across a page break),
    # keeping the richest row (one that resolved a lesson code / title).
    best: dict = {}
    for d in days:
        k = d["day"]
        if k not in best or (len(d["title"]) > len(best[k]["title"])):
            best[k] = d
    days = [best[k] for k in sorted(best)]
    if not days:
        return None
    if not head["pacing_start"]:
        head["pacing_start"] = days[0]["date"]
    if not head["pacing_end"]:
        head["pacing_end"] = days[-1]["date"]
    head["days"] = days
    return head
