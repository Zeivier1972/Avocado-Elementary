"""Parse the native i-Ready Diagnostic Results CSV export (Math or Reading).

One row per student per diagnostic window. Provides overall scale score,
placement, relative placement, percentile, grouping, and domain scale scores.
"""
from __future__ import annotations

import csv
import io


def _s(v) -> str:
    return ("" if v is None else str(v)).strip()


def _num(v):
    v = _s(v).replace("%", "")
    try:
        return float(v)
    except ValueError:
        return None


def placement_level(placement: str):
    """Map i-Ready relative placement to the district's 1/2/3 level, where the
    goal (Level 3+) = on grade level or above. i-Ready 'Grouping' is an
    instructional group number, NOT proficiency, so we use placement."""
    p = _s(placement).lower()
    if not p:
        return None
    if "above" in p or "on grade" in p:      # early/mid on grade, or above
        return 3
    if "1 grade level below" in p:
        return 2
    if "below" in p:                          # 2+ grade levels below
        return 1
    return None


def detect_iready(headers) -> bool:
    joined = ",".join(_s(h).lower() for h in headers)
    return "overall scale score" in joined and "overall placement" in joined


# i-Ready math domains -> short label
MATH_DOMAINS = {
    "Number and Operations": "NO",
    "Algebra and Algebraic Thinking": "ALG",
    "Measurement and Data": "MD",
    "Geometry": "GEO",
}
READING_DOMAINS = {
    "Phonological Awareness": "PA", "Phonics": "PH",
    "High-Frequency Words": "HFW", "Vocabulary": "VOC",
    "Comprehension: Literature": "CLIT", "Comprehension: Informational Text": "CINFO",
}


def parse_iready(data: bytes) -> dict:
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    subject = "MATH" if any("Number and Operations" in f for f in fields) else "ELA"
    domains = MATH_DOMAINS if subject == "MATH" else READING_DOMAINS

    students = []
    period = "AP1"
    for row in reader:
        sid = _s(row.get("Student ID")).lstrip("0")
        if not sid or not sid.isdigit():
            continue
        # window -> period
        baseline = _s(row.get("Baseline Diagnostic (Y/N)")).upper()
        norm = _s(row.get("Norming Window")).lower()
        if "winter" in norm:
            p = "AP2"
        elif "spring" in norm:
            p = "AP3"
        else:
            p = "AP1"
        period = p
        grade = _s(row.get("Student Grade")).upper()
        grade = "K" if grade in ("0", "K", "KG") else grade
        flags = {}
        if _s(row.get("English Language Learner")).upper() in ("Y", "YES"):
            flags["ell"] = "Y"
        if _s(row.get("Special Education")).upper() in ("Y", "YES"):
            flags["ese"] = True

        placement = _s(row.get("Overall Relative Placement"))
        percentile = _num(row.get("Percentile"))
        grouping = _num(row.get("Grouping"))
        domain_scores = {}
        for full, short in domains.items():
            ss = _num(row.get(f"{full} Scale Score"))
            pl = _s(row.get(f"{full} Relative Placement"))
            if ss is not None:
                domain_scores[short] = {"scale": ss, "placement": pl}

        students.append({
            "district_student_id": sid,
            "first_name": _s(row.get("First Name")), "last_name": _s(row.get("Last Name")),
            "grade": grade, "flags": flags,
            "scale_score": _num(row.get("Overall Scale Score")),
            "grouping": grouping, "percentile": percentile,
            "placement": placement,
            "level": placement_level(placement),  # 3 = on grade+ (goal)
            "teacher": _s(row.get("Class Teacher(s)")),
            "domains": domain_scores,
        })
    return {"students": students, "subject": subject, "period": period}
