"""Parse the school Staff Roster (.xlsx) into a section↔teacher directory.

We read the "CLASSROOM TEACHERS" sheet — one row per homeroom/section — and
normalize the grade text, the program (Gen Ed / ASD / ASD-Modified / Reverse),
and whether that teacher teaches math. Real names stay in the DB, never in the
repo.
"""
from __future__ import annotations

import io

import openpyxl


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


def _title(name: str) -> str:
    """Title-case a ROSTER name but keep small connectors and initials sane."""
    name = " ".join(name.split())
    if not name:
        return ""
    parts = []
    for w in name.split(" "):
        if "-" in w:
            parts.append("-".join(p.capitalize() for p in w.split("-")))
        elif "." in w and len(w) <= 3:  # initials like "M."
            parts.append(w.upper())
        else:
            parts.append(w.capitalize())
    return " ".join(parts)


def _grade_and_program(grade_text: str) -> tuple[str, str]:
    """Map a GRADE cell ('THIRD GRADE ASD M') to (grade, program)."""
    g = grade_text.upper()
    program = ""
    if "ASD M" in g or "ASD MOD" in g:
        program = "ASD-Modified"
    elif "REVERSE" in g:
        program = "Reverse"
    elif "ASD" in g:
        program = "ASD"

    if "KINDER" in g:
        grade = "K"
    elif "FIRST" in g:
        grade = "1"
    elif "SECOND" in g:
        grade = "2"
    elif "THIRD" in g:
        grade = "3"
    elif "VPK" in g:
        grade = "VPK"
    elif "PRE K" in g or "PREK" in g or "PRE-K" in g:
        grade = "PK"
    else:
        grade = grade_text.strip()
    return grade, program


def _teaches_math(subject: str) -> bool:
    s = subject.upper()
    return "MATH" in s or "ALL SUBJECT" in s


def _find_classroom_sheet(wb):
    for ws in wb.worksheets:
        if "CLASSROOM" in ws.title.upper() or "TEACHER" in ws.title.upper():
            return ws
    return wb.worksheets[0]


def _header_index(rows) -> tuple[int, dict]:
    """Find the header row and map known column names -> index."""
    wanted = {
        "grade": ["GRADE"], "section": ["SEC", "SEC.", "SECTION"],
        "room": ["ROOM"], "teacher": ["TEACHER", "NAME"],
        "subject": ["SUBJECT"], "ext": ["EXT"], "birthday": ["BIRTHDAY", "BIRTHDAYS"],
    }
    for i, row in enumerate(rows[:8]):
        upper = [_norm(c).upper() for c in row]
        if "TEACHER" in upper and ("GRADE" in upper or "SEC" in upper or "SEC." in upper):
            idx: dict = {}
            for key, names in wanted.items():
                for n in names:
                    if n in upper:
                        idx[key] = upper.index(n)
                        break
            return i, idx
    return -1, {}


def parse_staff_roster(data: bytes) -> dict:
    """Return {"staff": [...], "reason": str|None}. Each staff row:
    section, grade, program, name, room, role, teaches_math, ext, birthday."""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    except Exception as e:  # pragma: no cover
        return {"staff": [], "reason": f"could not open the file ({e})"}

    ws = _find_classroom_sheet(wb)
    rows = list(ws.iter_rows(values_only=True))
    hi, idx = _header_index(rows)
    if hi < 0 or "teacher" not in idx:
        return {"staff": [], "reason": "no CLASSROOM TEACHERS header row found"}

    def cell(row, key):
        j = idx.get(key)
        return _norm(row[j]) if j is not None and j < len(row) else ""

    staff = []
    last_grade_text = ""
    for row in rows[hi + 1:]:
        if not any(_norm(c) for c in row):
            continue
        name = cell(row, "teacher")
        grade_text = cell(row, "grade") or last_grade_text
        if grade_text:
            last_grade_text = grade_text
        # Skip subtotal / note rows that carry no real teacher name.
        if not name or name.upper() in ("TEACHER", "NAME"):
            continue
        subject = cell(row, "subject")
        grade, program = _grade_and_program(grade_text)
        staff.append({
            "section": cell(row, "section"),
            "grade": grade,
            "program": program,
            "name": _title(name),
            "room": cell(row, "room"),
            "role": subject,
            "teaches_math": _teaches_math(subject),
            "ext": cell(row, "ext"),
            "birthday": cell(row, "birthday"),
        })
    if not staff:
        return {"staff": [], "reason": "no teacher rows found under the header"}
    return {"staff": staff, "reason": None}


# Grades the math coach actively works with (used to flag the directory).
COACH_GRADES = {"K", "1", "2", "3"}
