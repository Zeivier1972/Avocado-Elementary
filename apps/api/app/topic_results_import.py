"""Parse a grade-wide topic-test RESULTS spreadsheet (one row per student, one
column per question) and score it against the test blueprint (answer key).

Tolerant by design: it auto-detects the student-name, student-id and
teacher/class columns, and the per-question columns (Q1, "1", "Item 1", the
Performance Matters "1-1".."1-19" form, or the bank item-id). Identity headers
and question headers may sit on DIFFERENT rows (as in a Performance Matters
export). Cell values may be the chosen letter (A/B/C/D, or "A,C,D" for
multi-select), or right/wrong as 1/0, correct/incorrect, ✓/✗.
"""
from __future__ import annotations

import io
import re

import openpyxl


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


def _clean_letters(v: str) -> str:
    """Normalize a chosen-answer cell to sorted unique letters, e.g. 'a c d'
    or 'ACD' -> 'A,C,D'. Non-letter answers return ''. """
    letters = sorted(set(re.findall(r"[A-Ea-e]", v)))
    return ",".join(x.upper() for x in letters)


_NAME_HINT = re.compile(r"student|name|last|first|pupil", re.I)
_ID_HINT = re.compile(r"\b(id|number|no\.?|mdcps|student\s*id)\b", re.I)
_CLASS_HINT = re.compile(r"teacher|class|section|homeroom|instructor", re.I)
# Q-column header: "Q1", "1", "Item 1", "#1", or the Performance Matters
# "1-1".."1-19" form (a leading part number then a dash) — the TRAILING number
# is the item position.
_QNUM = re.compile(r"^(?:q|item|question|#)?\s*(?:\d+\s*-\s*)?0*(\d{1,3})$", re.I)


def _detect_columns(header: list[str], items: list[dict]) -> dict:
    """Map roles -> column index. Question columns map to item POSITION."""
    id_by_item = {str(it.get("item_id", "")): it["position"] for it in items}
    positions = {it["position"] for it in items}
    name_col = id_col = class_col = None
    qcols: dict[int, int] = {}  # position -> column index
    for j, h in enumerate(header):
        hs = _norm(h)
        if not hs:
            continue
        # Question column?
        m = _QNUM.match(hs)
        if m and int(m.group(1)) in positions:
            qcols[int(m.group(1))] = j
            continue
        if hs in id_by_item:  # header is the bank item-id
            qcols[id_by_item[hs]] = j
            continue
        # Identity columns. Check ID first so "Student ID" is not mistaken for the
        # name column just because it contains the word "student".
        if id_col is None and _ID_HINT.search(hs):
            id_col = j
            continue
        if class_col is None and _CLASS_HINT.search(hs) and not _NAME_HINT.search(hs):
            class_col = j
            continue
        if name_col is None and _NAME_HINT.search(hs):
            name_col = j
            continue
    return {"name": name_col, "id": id_col, "class": class_col, "qcols": qcols}


def _find_header(rows: list[list], items: list[dict]) -> tuple[int, dict, int]:
    """Locate the header. The question-column header row and the identity
    (Student ID / Name / Teacher) header row may be DIFFERENT rows — Performance
    Matters puts the item labels ("1-1"..) on one row and "Student ID"/"Student
    Name" on the next. Returns (question_header_row, columns, data_start_row)
    where data begins at data_start_row + 1."""
    n = min(15, len(rows))
    # 1) Question header = the row that maps the most question columns.
    qrow, qcols = -1, {}
    for i in range(n):
        det = _detect_columns([_norm(c) for c in rows[i]], items)
        if len(det["qcols"]) > len(qcols):
            qrow, qcols = i, det["qcols"]
        if len(qcols) >= len(items):  # full match — stop early
            break
    if qrow < 0 or not qcols:
        return -1, {"qcols": {}, "name": None, "id": None, "class": None}, -1
    # 2) Identity columns may live on the question row or an adjacent header row.
    name_col = id_col = class_col = None
    last_hdr = qrow
    for i in range(max(0, qrow - 1), min(n, qrow + 3)):
        det = _detect_columns([_norm(c) for c in rows[i]], items)
        if id_col is None and det["id"] is not None:
            id_col, last_hdr = det["id"], max(last_hdr, i)
        if name_col is None and det["name"] is not None:
            name_col, last_hdr = det["name"], max(last_hdr, i)
        if class_col is None and det["class"] is not None:
            class_col, last_hdr = det["class"], max(last_hdr, i)
    return qrow, {"qcols": qcols, "name": name_col, "id": id_col,
                  "class": class_col}, last_hdr


def _is_correct(cell: str, correct: str) -> bool | None:
    """True/False if we can tell, else None (blank/unreadable)."""
    c = cell.strip()
    if c == "":
        return None
    low = c.lower()
    # Right/wrong encodings (a bare letter A-E is treated as a chosen answer
    # below, never as correctness).
    if low in ("1", "1.0", "y", "yes", "correct", "true", "✓", "✔", "right"):
        return True
    if low in ("0", "0.0", "n", "no", "incorrect", "false", "✗", "✘", "x", "wrong"):
        return False
    # Chosen-answer encoding (letters).
    chosen = _clean_letters(c)
    if chosen:
        return chosen == (correct or "")
    return None


_STD_CODE = re.compile(r"([A-Z]{2,4}\.[K0-9]+\.[A-Z]+\.\d+\.\d+)", re.I)


def _pct(v: str):
    """A percent cell ('83%', '0.83', '83') -> float 0-100, or None."""
    raw = _norm(v)
    if not raw:
        return None
    has_pct = "%" in raw
    try:
        f = float(raw.replace("%", "").strip())
    except ValueError:
        return None
    if not has_pct and 0 < f <= 1:
        f *= 100  # a fraction like 0.83
    return round(f, 1)


def _parse_benchmark_summary(rows: list[list], items: list[dict]) -> dict:
    """Fallback for a Performance Matters 'Student Results' export that has NO
    per-question columns — just a Student Name, Student Id, Total Score and one
    percent column PER BENCHMARK (e.g. 'FL.20.BEST.MA.3.AR.1.1'). We can't know
    which individual questions were missed, but we CAN store each student's
    per-standard proficiency (so class averages, the weakest-standard DI target
    and Red/Yellow/Green tiers all work). Points are reconstructed from the test
    blueprint so the numbers line up with the rest of the system."""
    # Point total per standard, from the answer key (scored items only).
    std_possible: dict = {}
    for it in items:
        if it.get("scored"):
            std_possible[it.get("standard", "")] = (
                std_possible.get(it.get("standard", ""), 0.0) + it.get("points", 0))
    test_stds = {s for s in std_possible if s}
    if not test_stds:
        return {"rows": []}

    # Find the header row: has a name-ish and id-ish column and >=1 benchmark col
    # whose extracted standard code is one of THIS test's standards.
    hdr_i = None
    name_col = id_col = total_col = None
    std_cols: dict = {}  # column index -> standard code
    for i in range(min(15, len(rows))):
        r = [_norm(c) for c in rows[i]]
        nc = ic = tc = None
        sc: dict = {}
        for j, h in enumerate(r):
            if not h:
                continue
            m = _STD_CODE.search(h)
            if m and m.group(1).upper() in test_stds:
                sc[j] = m.group(1).upper()
                continue
            if ic is None and _ID_HINT.search(h):
                ic = j
                continue
            if tc is None and re.search(r"total", h, re.I):
                tc = j
                continue
            if nc is None and _NAME_HINT.search(h):
                nc = j
        if sc and (nc is not None or ic is not None):
            hdr_i, name_col, id_col, total_col, std_cols = i, nc, ic, tc, sc
            break
    if hdr_i is None or not std_cols:
        return {"rows": []}

    out = []
    for row in rows[hdr_i + 1:]:
        if not any(_norm(c) for c in row):
            continue
        def cell(j):
            return _norm(row[j]) if j is not None and j < len(row) else ""
        name, sid = cell(name_col), cell(id_col)
        if not name and not sid:
            continue
        by_std: dict = {}
        earned = possible = 0.0
        for j, code in std_cols.items():
            poss = std_possible.get(code, 0.0)
            if not poss:
                continue
            p = _pct(cell(j))
            if p is None:
                continue
            e = round(poss * p / 100.0, 2)
            by_std[code] = {"earned": e, "possible": poss}
            earned += e
            possible += poss
        if not by_std:
            continue
        total = _pct(cell(total_col))
        pct = total if total is not None else (
            round(100.0 * earned / possible, 1) if possible else 0.0)
        out.append({
            "student_name": name, "student_id": sid, "teacher_name": "",
            "points_earned": round(earned, 2), "points_possible": round(possible, 2),
            "percent": pct, "answered": len(by_std),
            "by_standard": by_std, "missed_positions": [],
        })
    if not out:
        return {"rows": []}
    return {"rows": out, "reason": None,
            "detected": {"format": "benchmark_summary",
                         "standards_matched": len(std_cols),
                         "item_level": False}}


def parse_results(data: bytes, items: list[dict]) -> dict:
    """Score a results workbook against the blueprint items. Returns
    {"rows": [...per student...], "reason", "detected"}."""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    except Exception as e:  # pragma: no cover
        return {"rows": [], "reason": f"could not open the spreadsheet ({e})"}
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return {"rows": [], "reason": "the spreadsheet is empty"}

    hi, det, data_start = _find_header(rows, items)
    if hi < 0 or not det["qcols"]:
        # No per-question columns — try the per-benchmark summary export.
        summary = _parse_benchmark_summary(rows, items)
        if summary.get("rows"):
            return summary
        return {"rows": [], "reason": "could not find question columns (Q1, Q2 …) "
                                      "matching the test, or benchmark % columns "
                                      "(e.g. MA.3.AR.1.1) for this test"}
    item_by_pos = {it["position"]: it for it in items}
    qcols = det["qcols"]

    out = []
    for row in rows[data_start + 1:]:
        if not any(_norm(c) for c in row):
            continue
        def cell(j):
            return _norm(row[j]) if j is not None and j < len(row) else ""
        name = cell(det["name"])
        sid = cell(det["id"])
        if not name and not sid:
            continue  # not a student row
        earned = possible = 0.0
        by_std: dict = {}
        missed: list = []
        answered = 0
        for pos, j in qcols.items():
            it = item_by_pos.get(pos)
            if not it or not it.get("scored"):
                continue
            possible += it["points"]
            std = it.get("standard", "")
            e = by_std.setdefault(std, {"earned": 0.0, "possible": 0.0})
            e["possible"] += it["points"]
            ok = _is_correct(cell(j), it.get("correct_response", ""))
            if ok is None:
                continue
            answered += 1
            if ok:
                earned += it["points"]
                e["earned"] += it["points"]
            else:
                missed.append(pos)
        pct = round(100.0 * earned / possible, 1) if possible else 0.0
        out.append({
            "student_name": name, "student_id": sid,
            "teacher_name": cell(det["class"]),
            "points_earned": earned, "points_possible": possible,
            "percent": pct, "answered": answered,
            "by_standard": by_std, "missed_positions": sorted(missed),
        })
    if not out:
        return {"rows": [], "reason": "no student rows found under the header"}
    return {"rows": out, "reason": None,
            "detected": {"questions_matched": len(qcols),
                         "has_teacher_col": det["class"] is not None}}
