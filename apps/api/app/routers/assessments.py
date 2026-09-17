"""Assessment import — the core 'data in -> instruction out' path.

Accepts a CSV (student_district_id, standard_code, percent_correct), records
results, recomputes per-standard mastery, and auto-forms DI groups for
deficient standards. This is the engine behind docs/03 (DI module).
"""
import csv
import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import audit, get_current_user
from app.models import (
    AssessmentDefinition,
    AssessmentResult,
    ClassRoom,
    DiGroup,
    DiGroupMember,
    Enrollment,
    Standard,
    StandardMastery,
    Student,
    User,
)

router = APIRouter(prefix="/assessments", tags=["assessments"])


@router.post("/import")
async def import_assessment(
    name: str = Form(...),
    source: str = Form("EXIT_TICKET"),
    subject: str = Form("ELA"),
    grade_level: str = Form("3"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    raw = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    required = {"student_district_id", "standard_code", "percent_correct"}
    if not required.issubset({c.strip() for c in (reader.fieldnames or [])}):
        raise HTTPException(
            400, f"CSV must have columns: {', '.join(sorted(required))}"
        )

    assessment = AssessmentDefinition(
        tenant_id=user.tenant_id, school_id=user.school_id or "",
        name=name, source=source, subject=subject.upper(),
        grade_level=grade_level,
    )
    db.add(assessment)
    db.flush()

    # Index lookups.
    students = {
        s.district_student_id: s
        for s in db.query(Student).filter(Student.tenant_id == user.tenant_id).all()
    }
    standards = {s.code: s for s in db.query(Standard).all()}

    imported, errors, touched = 0, [], set()
    for i, row in enumerate(reader, start=2):
        sid = row.get("student_district_id", "").strip()
        code = row.get("standard_code", "").strip()
        try:
            pct = float(row.get("percent_correct", "").strip())
            if pct > 1:  # accept 0-100 or 0-1
                pct = pct / 100.0
        except ValueError:
            errors.append(f"row {i}: bad percent_correct")
            continue
        student = students.get(sid)
        standard = standards.get(code)
        if not student:
            errors.append(f"row {i}: unknown student {sid}")
            continue
        if not standard:
            errors.append(f"row {i}: unknown standard {code}")
            continue

        db.add(AssessmentResult(
            tenant_id=user.tenant_id, assessment_id=assessment.id,
            student_id=student.id, standard_id=standard.id, percent_correct=pct,
        ))
        _update_mastery(db, user.tenant_id, student.id, standard, pct)
        touched.add(standard.id)
        imported += 1

    db.commit()
    audit(db, actor=user, action="import", entity_type="assessment",
          entity_id=assessment.id, purpose="assessment_import")

    groups = _autoform_groups(db, user, list(touched))
    db.commit()

    return {
        "assessment_id": assessment.id,
        "imported": imported,
        "errors": errors,
        "standards_touched": len(touched),
        "groups_formed": groups,
    }


def _update_mastery(db: Session, tenant_id: str, student_id: str,
                    standard: Standard, pct: float) -> None:
    m = (
        db.query(StandardMastery)
        .filter(StandardMastery.student_id == student_id,
                StandardMastery.standard_id == standard.id)
        .first()
    )
    prev = m.mastery_pct if m else None
    status = ("mastered" if pct >= standard.mastery_threshold
              else "deficient" if pct < 0.5 else "in_progress")
    trend = "flat"
    if prev is not None:
        trend = "up" if pct > prev + 0.02 else "down" if pct < prev - 0.02 else "flat"
    if m:
        m.mastery_pct, m.status, m.trend = pct, status, trend
    else:
        db.add(StandardMastery(
            tenant_id=tenant_id, student_id=student_id, standard_id=standard.id,
            mastery_pct=pct, status=status, trend=trend,
        ))


def _autoform_groups(db: Session, user: User, standard_ids: list[str]) -> list[dict]:
    """For each teacher class, group deficient students by shared standard."""
    formed = []
    classes = db.query(ClassRoom).filter(ClassRoom.teacher_id == user.id).all()
    for cls in classes:
        enrolled = {
            r[0] for r in db.query(Enrollment.student_id)
            .filter(Enrollment.class_id == cls.id).all()
        }
        if not enrolled:
            continue
        for std_id in standard_ids:
            deficient = (
                db.query(StandardMastery)
                .filter(StandardMastery.standard_id == std_id,
                        StandardMastery.student_id.in_(enrolled),
                        StandardMastery.status == "deficient")
                .all()
            )
            if not deficient:
                continue
            std = db.get(Standard, std_id)
            # Replace any existing draft group for this class+standard.
            db.query(DiGroup).filter(
                DiGroup.class_id == cls.id, DiGroup.standard_id == std_id,
                DiGroup.status == "draft",
            ).delete()
            group = DiGroup(
                tenant_id=user.tenant_id, class_id=cls.id, standard_id=std_id,
                name=f"{std.code} reteach", status="draft",
            )
            db.add(group)
            db.flush()
            for m in deficient:
                db.add(DiGroupMember(di_group_id=group.id, student_id=m.student_id))
            formed.append({"class": cls.name, "standard": std.code,
                           "size": len(deficient)})
    return formed
