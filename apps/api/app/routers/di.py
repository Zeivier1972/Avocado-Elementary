"""Differentiated Instruction: view auto-formed groups and generate 7-day plans."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai import generate_di_plan
from app.db.session import get_db
from app.deps import audit, get_current_user
from app.models import (
    ClassRoom,
    DiGroup,
    DiGroupMember,
    Standard,
    Student,
    User,
)

router = APIRouter(prefix="/di", tags=["differentiated-instruction"])


@router.get("/groups")
def list_groups(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    class_ids = [
        c.id for c in db.query(ClassRoom).filter(ClassRoom.teacher_id == user.id).all()
    ]
    groups = (
        db.query(DiGroup)
        .filter(DiGroup.class_id.in_(class_ids))
        .order_by(DiGroup.created_at.desc())
        .all()
    ) if class_ids else []
    out = []
    for g in groups:
        std = db.get(Standard, g.standard_id)
        members = (
            db.query(DiGroupMember, Student)
            .join(Student, Student.id == DiGroupMember.student_id)
            .filter(DiGroupMember.di_group_id == g.id)
            .all()
        )
        out.append({
            "id": g.id,
            "name": g.name,
            "status": g.status,
            "standard": {"code": std.code, "subject": std.subject,
                         "description": std.description} if std else None,
            "members": [
                {"student_id": s.id, "name": f"{s.first_name} {s.last_name}",
                 "added_by": m.added_by}
                for m, s in members
            ],
        })
    return out


@router.post("/groups/{group_id}/plan")
def generate_plan(
    group_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate a 7-day DI plan for the group (docs/03 cycle). AI-grounded when
    a provider is configured; otherwise a structured template is returned."""
    g = db.get(DiGroup, group_id)
    if not g:
        raise HTTPException(404, "Group not found")
    std = db.get(Standard, g.standard_id)
    members = (
        db.query(Student)
        .join(DiGroupMember, DiGroupMember.student_id == Student.id)
        .filter(DiGroupMember.di_group_id == g.id)
        .all()
    )
    audit(db, actor=user, action="generate", entity_type="di_plan",
          entity_id=g.id, purpose="di_plan_generation")

    plan = generate_di_plan(
        standard={"code": std.code, "description": std.description,
                  "subject": std.subject, "grade_level": std.grade_level,
                  "details": std.details or {}},
        group_size=len(members),
        # de-identified: only attributes, never names, go to the model
        student_profiles=[{"grade": s.grade_level, "flags": s.flags or {}}
                          for s in members],
    )
    return {"group_id": g.id, "standard": std.code, "plan": plan}
