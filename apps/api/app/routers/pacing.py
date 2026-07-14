"""District pacing calendar — the backbone of collaborative planning."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user
from app.models import PacingTopic, Standard, User

router = APIRouter(prefix="/pacing", tags=["pacing"])


def _resolve_standards(db: Session, codes: list[str]) -> list[dict]:
    out = []
    for code in codes:
        s = db.query(Standard).filter(Standard.code == code).first()
        if s:
            d = s.details or {}
            out.append({
                "code": s.code, "subject": s.subject, "grade_level": s.grade_level,
                "description": s.description,
                "misconceptions": d.get("misconceptions", ""),
                "clarifications": d.get("clarifications", []),
                "prerequisites": d.get("prerequisites", []),
                "next": d.get("next", []),
            })
        else:
            out.append({"code": code, "description": "(not yet loaded)"})
    return out


@router.get("")
def list_topics(
    grade: str | None = None,
    subject: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(PacingTopic)
    if grade:
        q = q.filter(PacingTopic.grade_level == grade)
    if subject:
        q = q.filter(PacingTopic.subject == subject.upper())
    topics = q.order_by(PacingTopic.grade_level, PacingTopic.week_order).all()
    return [
        {
            "id": t.id, "topic_code": t.topic_code, "chapter": t.chapter,
            "name": t.name, "subject": t.subject, "grade_level": t.grade_level,
            "quarter": t.quarter, "benchmarks": t.benchmarks,
            "learning_target": t.learning_target,
        }
        for t in topics
    ]


@router.get("/{topic_id}")
def get_topic(
    topic_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    t = db.get(PacingTopic, topic_id)
    if not t:
        raise HTTPException(404, "Pacing topic not found")
    return {
        "id": t.id, "topic_code": t.topic_code, "chapter": t.chapter,
        "name": t.name, "subject": t.subject, "grade_level": t.grade_level,
        "quarter": t.quarter, "learning_target": t.learning_target,
        "success_criteria": t.success_criteria, "vocabulary": t.vocabulary,
        "source": t.source,
        "standards": _resolve_standards(db, t.benchmarks),
    }
