"""Student roster and profile endpoints, RBAC-scoped with audit logging."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import audit, get_current_user
from app.models import (
    ClassRoom,
    Enrollment,
    Standard,
    StandardMastery,
    Student,
    User,
)

router = APIRouter(prefix="/students", tags=["students"])


def _visible_student_ids(db: Session, user: User) -> set[str] | None:
    """Return the set of student ids the user may see, or None for 'all in school'.

    Teachers see only students enrolled in their classes. School-level roles
    (principal/AP) see the whole school. This is the RBAC seam described in
    docs/06-system-architecture.md; production enforces it at the DB layer too.
    """
    if user.role in {"principal", "ap", "district_admin"}:
        return None  # all within their school/tenant (filtered below)
    if user.role in {"teacher", "interventionist", "ese_teacher", "ell_teacher"}:
        rows = (
            db.query(Enrollment.student_id)
            .join(ClassRoom, ClassRoom.id == Enrollment.class_id)
            .filter(ClassRoom.teacher_id == user.id)
            .all()
        )
        return {r[0] for r in rows}
    return set()  # coaches/support: no direct roster in this MVP slice


@router.get("")
def list_students(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Student).filter(Student.tenant_id == user.tenant_id)
    if user.school_id:
        q = q.filter(Student.school_id == user.school_id)
    visible = _visible_student_ids(db, user)
    if visible is not None:
        if not visible:
            return []
        q = q.filter(Student.id.in_(visible))
    return [_serialize(s) for s in q.order_by(Student.last_name).all()]


@router.get("/{student_id}")
def get_student(
    student_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = db.get(Student, student_id)
    if not s or s.tenant_id != user.tenant_id:
        raise HTTPException(404, "Student not found")
    visible = _visible_student_ids(db, user)
    if visible is not None and s.id not in visible:
        raise HTTPException(403, "Not authorized for this student")

    audit(db, actor=user, action="read", entity_type="student",
          entity_id=s.id, purpose="student_profile")

    mastery = (
        db.query(StandardMastery, Standard)
        .join(Standard, Standard.id == StandardMastery.standard_id)
        .filter(StandardMastery.student_id == s.id)
        .all()
    )
    return {
        **_serialize(s),
        "mastery": [
            {
                "standard_code": std.code,
                "subject": std.subject,
                "status": m.status,
                "mastery_pct": round(m.mastery_pct, 2),
                "trend": m.trend,
            }
            for m, std in mastery
        ],
    }


def _serialize(s: Student) -> dict:
    return {
        "id": s.id,
        "district_student_id": s.district_student_id,
        "first_name": s.first_name,
        "last_name": s.last_name,
        "grade_level": s.grade_level,
        "flags": s.flags or {},
    }
