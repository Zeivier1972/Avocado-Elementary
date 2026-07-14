"""Coach section — collaborative planning: pacing calendar + PLC agendas."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai import generate_planning_guide, generate_plc_agenda
from app.db.session import get_db
from app.deps import audit, get_current_user
from app.models import PacingTopic, PlcAgenda, User
from app.routers.pacing import _resolve_standards

router = APIRouter(prefix="/coach", tags=["coach"])

COACH_ROLES = {"reading_coach", "math_coach", "instructional_coach",
               "principal", "ap", "district_admin"}


def _require_coach(user: User = Depends(get_current_user)) -> User:
    if user.role not in COACH_ROLES:
        raise HTTPException(403, "Coach/leadership role required")
    return user


@router.get("/dashboard")
def coach_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Upcoming planning weeks the coach can prep, scoped to their subject."""
    q = db.query(PacingTopic).filter(PacingTopic.tenant_id == user.tenant_id)
    scope = user.scope or {}
    subjects = scope.get("subjects")
    if user.role == "math_coach":
        subjects = ["MATH"]
    elif user.role == "reading_coach":
        subjects = ["ELA"]
    if subjects:
        q = q.filter(PacingTopic.subject.in_([s.upper() for s in subjects]))
    topics = q.order_by(PacingTopic.grade_level, PacingTopic.week_order).all()
    return {
        "role": user.role,
        "subjects": subjects or ["MATH", "ELA"],
        "planning_weeks": [
            {
                "id": t.id, "topic_code": t.topic_code, "chapter": t.chapter,
                "name": t.name, "grade_level": t.grade_level,
                "subject": t.subject, "quarter": t.quarter,
                "learning_target": t.learning_target,
                "benchmark_count": len(t.benchmarks or []),
            }
            for t in topics
        ],
    }


@router.post("/agenda/{topic_id}")
def generate_agenda(
    topic_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Generate an AI collaborative-planning agenda for a pacing week, grounded
    in that week's real benchmarks, learning target and misconceptions."""
    t = db.get(PacingTopic, topic_id)
    if not t:
        raise HTTPException(404, "Pacing topic not found")
    standards = _resolve_standards(db, t.benchmarks)
    topic_ctx = {
        "topic_code": t.topic_code, "chapter": t.chapter, "name": t.name,
        "grade_level": t.grade_level, "subject": t.subject, "quarter": t.quarter,
        "learning_target": t.learning_target,
        "success_criteria": t.success_criteria, "vocabulary": t.vocabulary,
    }
    agenda = generate_plc_agenda(topic_ctx, standards)

    record = PlcAgenda(
        tenant_id=user.tenant_id, pacing_topic_id=t.id, created_by=user.id,
        content=agenda, ai_generated=agenda.get("ai_generated", False),
    )
    db.add(record)
    db.commit()
    audit(db, actor=user, action="generate", entity_type="plc_agenda",
          entity_id=record.id, purpose="collaborative_planning")
    return {"topic": t.name, "agenda": agenda}


@router.post("/guide/{topic_id}")
def generate_guide(
    topic_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Generate a full lesson-by-lesson Collaborative Planning Guide for a topic,
    grounded in the pacing guide + B1G-M benchmark content."""
    t = db.get(PacingTopic, topic_id)
    if not t:
        raise HTTPException(404, "Pacing topic not found")
    standards = _resolve_standards(db, t.benchmarks)
    topic_ctx = {
        "topic_code": t.topic_code, "chapter": t.chapter, "name": t.name,
        "grade_level": t.grade_level, "subject": t.subject, "quarter": t.quarter,
        "learning_target": t.learning_target,
        "success_criteria": t.success_criteria, "vocabulary": t.vocabulary,
        "time_frame": t.time_frame, "topic_focus": t.topic_focus,
        "ald_focus": t.ald_focus, "mtr_practices": t.mtr_practices,
        "materials": t.materials, "lessons": t.lessons,
    }
    guide = generate_planning_guide(topic_ctx, standards)
    record = PlcAgenda(
        tenant_id=user.tenant_id, pacing_topic_id=t.id, created_by=user.id,
        content=guide, ai_generated=guide.get("ai_generated", False),
    )
    db.add(record)
    db.commit()
    audit(db, actor=user, action="generate", entity_type="planning_guide",
          entity_id=record.id, purpose="collaborative_planning")
    return {"topic": t.name, "guide": guide}
