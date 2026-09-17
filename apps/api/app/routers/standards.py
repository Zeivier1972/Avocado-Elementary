"""Standards library endpoints (Florida B.E.S.T.)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user
from app.models import Standard, User

router = APIRouter(prefix="/standards", tags=["standards"])


@router.get("")
def list_standards(
    subject: str | None = None,
    grade_level: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Standard)
    if subject:
        q = q.filter(Standard.subject == subject.upper())
    if grade_level:
        q = q.filter(Standard.grade_level == grade_level)
    return [_serialize(s) for s in q.order_by(Standard.code).all()]


@router.get("/{standard_id}")
def get_standard(
    standard_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    s = db.get(Standard, standard_id)
    if not s:
        raise HTTPException(404, "Standard not found")
    return _serialize(s, full=True)


def _serialize(s: Standard, full: bool = False) -> dict:
    out = {
        "id": s.id,
        "code": s.code,
        "subject": s.subject,
        "grade_level": s.grade_level,
        "description": s.description,
        "mastery_threshold": s.mastery_threshold,
    }
    if full:
        out["details"] = s.details or {}
    return out
