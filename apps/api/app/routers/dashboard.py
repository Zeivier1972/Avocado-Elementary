"""Role dashboards. MVP implements the teacher and principal views that power
the wireframes in docs/08-dashboard-designs.md."""
from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user
from app.models import (
    ClassRoom,
    Enrollment,
    Standard,
    StandardMastery,
    Student,
    User,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

WATCH = 0.6   # below this mastery rate => 🟡
RISK = 0.5    # below this => 🔴


def _band(pct: float) -> str:
    if pct >= WATCH:
        return "on_track"
    if pct >= RISK:
        return "watch"
    return "at_risk"


@router.get("/teacher")
def teacher_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Class snapshot: proficiency, lowest standards, recommended DI groups,
    and intervention vs. enrichment lists — the teacher's primary screen."""
    classes = db.query(ClassRoom).filter(ClassRoom.teacher_id == user.id).all()
    class_ids = [c.id for c in classes]
    student_ids = [
        r[0]
        for r in db.query(Enrollment.student_id)
        .filter(Enrollment.class_id.in_(class_ids))
        .all()
    ] if class_ids else []

    if not student_ids:
        return {"classes": [], "proficiency": None, "lowest_standards": [],
                "recommended_groups": [], "needs_intervention": [],
                "needs_enrichment": []}

    rows = (
        db.query(StandardMastery, Standard, Student)
        .join(Standard, Standard.id == StandardMastery.standard_id)
        .join(Student, Student.id == StandardMastery.student_id)
        .filter(StandardMastery.student_id.in_(student_ids))
        .all()
    )

    # Per-standard aggregate mastery.
    by_standard: dict[str, list] = defaultdict(list)
    for m, std, _stu in rows:
        by_standard[std.id].append((m, std))

    lowest = []
    for std_id, items in by_standard.items():
        std = items[0][1]
        avg = sum(m.mastery_pct for m, _ in items) / len(items)
        deficient = [m for m, _ in items if m.status == "deficient"]
        lowest.append({
            "standard_id": std_id,
            "code": std.code,
            "subject": std.subject,
            "avg_mastery": round(avg, 2),
            "band": _band(avg),
            "students_deficient": len(deficient),
        })
    lowest.sort(key=lambda x: x["avg_mastery"])

    overall = sum(m.mastery_pct for m, _, _ in rows) / len(rows)

    # Recommended DI groups: the two lowest standards with deficient students.
    recommended = [
        {"standard_code": s["code"], "subject": s["subject"],
         "size": s["students_deficient"], "band": s["band"]}
        for s in lowest if s["students_deficient"] > 0
    ][:3]

    # Intervention vs enrichment by student average.
    per_student: dict[str, list[float]] = defaultdict(list)
    names: dict[str, Student] = {}
    for m, _std, stu in rows:
        per_student[stu.id].append(m.mastery_pct)
        names[stu.id] = stu
    needs_intervention, needs_enrichment = [], []
    for sid, pcts in per_student.items():
        avg = sum(pcts) / len(pcts)
        entry = {"student_id": sid,
                 "name": f"{names[sid].first_name} {names[sid].last_name}",
                 "avg_mastery": round(avg, 2)}
        if avg < RISK:
            needs_intervention.append(entry)
        elif avg >= 0.85:
            needs_enrichment.append(entry)
    needs_intervention.sort(key=lambda x: x["avg_mastery"])
    needs_enrichment.sort(key=lambda x: -x["avg_mastery"])

    return {
        "classes": [{"id": c.id, "name": c.name, "subject": c.subject,
                     "grade_level": c.grade_level} for c in classes],
        "proficiency": {"overall": round(overall, 2), "band": _band(overall)},
        "lowest_standards": lowest[:5],
        "recommended_groups": recommended,
        "needs_intervention": needs_intervention[:8],
        "needs_enrichment": needs_enrichment[:8],
    }


@router.get("/principal")
def principal_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """School health: proficiency by subject and standards needing remediation."""
    rows = (
        db.query(StandardMastery, Standard)
        .join(Standard, Standard.id == StandardMastery.standard_id)
        .filter(StandardMastery.tenant_id == user.tenant_id)
        .all()
    )
    if not rows:
        return {"health": None, "standards_needing_remediation": []}

    subj: dict[str, list[float]] = defaultdict(list)
    by_standard: dict[str, list] = defaultdict(list)
    for m, std in rows:
        subj[std.subject].append(m.mastery_pct)
        by_standard[std.id].append((m, std))

    health = {
        s: {"proficiency": round(sum(v) / len(v), 2),
            "band": _band(sum(v) / len(v))}
        for s, v in subj.items()
    }
    remediation = []
    for std_id, items in by_standard.items():
        std = items[0][1]
        avg = sum(m.mastery_pct for m, _ in items) / len(items)
        remediation.append({"code": std.code, "subject": std.subject,
                            "avg_mastery": round(avg, 2), "band": _band(avg)})
    remediation.sort(key=lambda x: x["avg_mastery"])

    return {"health": health, "standards_needing_remediation": remediation[:8]}
