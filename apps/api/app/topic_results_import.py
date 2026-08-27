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
        return {"rows": [], "reason": "could not find question columns (Q1, Q2 …) "
                                      "matching the test"}
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
