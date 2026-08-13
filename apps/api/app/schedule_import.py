"""Parse the Avocado Master Schedule workbook into per-teacher Math and Math-DI
time blocks.

The workbook lays each grade's teachers out in day-rows (M/T/W/R/F). Row 3 holds
5-minute time columns; each subject is a horizontally-merged block. For the math
coach we extract, per teacher per day:
  - MATH blocks  → when to visit a math lesson
  - SCIENCE / SOCIAL STUDIES blocks → the window a math teacher can run Math DI
    (per the coach: DI happens during science/social-studies time).
"""
from __future__ import annotations

import io
import re
from collections import defaultdict

DAY_MAP = {"M": "Mon", "T": "Tue", "W": "Wed", "R": "Thu", "F": "Fri"}
DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri"]
# K-3 homeroom sheets (the coach supports K-3 math). Others (ASD/ESE/PreK) can be
# added later; the parser itself is sheet-agnostic.
DEFAULT_SHEETS = ["Kinder & Grade 1", "Grade  2 & 3"]


def _hhmm(v) -> str | None:
    return f"{v.hour:02d}:{v.minute:02d}" if hasattr(v, "hour") else None


def _plus5(v) -> str:
    m = v.hour * 60 + v.minute + 5
    return f"{m // 60:02d}:{m % 60:02d}"


def _classify(label: str) -> str | None:
    u = label.upper()
    if re.search(r"\bMATHEMATICS\b|\bMATH\b", u) and "CP" not in u:
        return "math"
    if "SCIENCE" in u or "SOCIAL" in u:
        return "di"
    return None


def _clean_subject(label: str) -> str:
    # drop the parenthetical co-teach / concurrency notes for a clean chip
    return re.sub(r"\s+", " ", label.split("(")[0]).strip()


def _parse_sheet(ws, grade_default=""):
    col_time = {c: ws.cell(3, c).value for c in range(1, ws.max_column + 1)
                if hasattr(ws.cell(3, c).value, "hour")}
    if not col_time:
        return []
    tmin = min(col_time)
    starts = defaultdict(list)
    for mr in ws.merged_cells.ranges:
        if mr.min_row == mr.max_row and mr.min_col >= tmin:
            starts[mr.min_row].append((mr.min_col, mr.max_col))

    def blocks(r):
        out, seen = [], set()
        for a, b in sorted(starts.get(r, [])):
            v = ws.cell(r, a).value
            if v is not None and str(v).strip():
                out.append((a, b, str(v).strip()))
                seen.update(range(a, b + 1))
        for c in sorted(col_time):
            if c in seen:
                continue
            v = ws.cell(r, c).value
            if v is not None and str(v).strip():
                out.append((c, c, str(v).strip()))
        return sorted(out)

    teachers = []
    grade = grade_default
    r = 4
    while r <= ws.max_row:
        a = ws.cell(r, 1).value
        if a and re.search(r"grade|kinder|prek|pre-k", str(a), re.I):
            grade = _norm_grade(str(a))
        b = ws.cell(r, 2).value
        day = ws.cell(r, 3).value
        if b and str(b).strip() and day:  # Monday row starts a teacher block
            binfo = re.sub(r"\s+", " ", str(b)).strip()
            mroom = re.match(r"^([A-Z]?\d{2,3}[A-Z]?)", binfo)
            room = mroom.group(1) if mroom else ""
            name = binfo[len(room):] if room else binfo
            name = re.split(r"\(|Room|ESOL|LV|SPED|/", name)[0].strip(" -·")
            days = {}
            for k in range(5):
                rr = r + k
                d = ws.cell(rr, 3).value
                if not d:
                    break
                dd = DAY_MAP.get(str(d).strip(), str(d).strip())
                math, di = [], []
                for x, y, val in blocks(rr):
                    kind = _classify(val)
                    if kind == "math":
                        math.append({"start": _hhmm(col_time[x]), "end": _plus5(col_time[y])})
                    elif kind == "di":
                        di.append({"subject": _clean_subject(val),
                                   "start": _hhmm(col_time[x]), "end": _plus5(col_time[y])})
                days[dd] = {"math": math, "di": di}
            teachers.append({"grade": grade, "room": room, "teacher": name,
                             "teaches_math": any(days[d]["math"] for d in days),
                             "days": days})
            r += 5
        else:
            r += 1
    return teachers


def _norm_grade(raw: str) -> str:
    r = raw.strip().lower()
    if "kinder" in r:
        return "K"
    m = re.search(r"(\d+)", r)
    return m.group(1) if m else raw.strip()


def parse_master_schedule(data: bytes, sheets: list[str] | None = None) -> dict:
    """Return {'teachers': [...], 'sheets_used': [...], 'reason': str|None}."""
    try:
        import openpyxl
    except ImportError:
        return {"teachers": [], "sheets_used": [], "reason": "openpyxl not installed"}
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    except Exception as e:
        return {"teachers": [], "sheets_used": [],
                "reason": f"could not open workbook: {type(e).__name__}"}
    want = sheets or DEFAULT_SHEETS
    # tolerant sheet matching (trailing/double spaces vary)
    norm = {re.sub(r"\s+", " ", s).strip().lower(): s for s in wb.sheetnames}
    teachers, used = [], []
    for target in want:
        key = re.sub(r"\s+", " ", target).strip().lower()
        real = norm.get(key)
        if real:
            teachers.extend(_parse_sheet(wb[real]))
            used.append(real)
    if not teachers:
        return {"teachers": [], "sheets_used": used,
                "reason": "no teacher rows found on the K-3 schedule sheets"}
    return {"teachers": teachers, "sheets_used": used, "reason": None}


def to_blocks(teachers: list[dict]) -> list[dict]:
    """Flatten parsed teachers into storable rows (one per math/di block)."""
    rows = []
    for t in teachers:
        for day, sub in t["days"].items():
            for m in sub["math"]:
                rows.append({"grade": t["grade"], "room": t["room"],
                             "teacher": t["teacher"], "day": day, "kind": "math",
                             "subject": "Mathematics",
                             "start": m["start"], "end": m["end"]})
            for d in sub["di"]:
                rows.append({"grade": t["grade"], "room": t["room"],
                             "teacher": t["teacher"], "day": day, "kind": "di",
                             "subject": d["subject"],
                             "start": d["start"], "end": d["end"]})
    return rows
