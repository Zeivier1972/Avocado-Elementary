"""Pacing calendar — day-by-day lesson schedule per grade, generated from the
topics' lesson sequences so coaches can track whether they're on pace."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import audit, get_current_user
from app.models import CalendarEntry, District, PacingTopic, User

router = APIRouter(prefix="/coach/calendar", tags=["calendar"])

COACH_ROLES = {"reading_coach", "math_coach", "instructional_coach",
               "principal", "ap", "district_admin"}


def _require_coach(user: User = Depends(get_current_user)) -> User:
    if user.role not in COACH_ROLES:
        raise HTTPException(403, "Coach/leadership role required")
    return user


def _weekday(d: date) -> date:
    """Roll forward to the next weekday (skip Sat/Sun)."""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _next(d: date) -> date:
    return _weekday(d + timedelta(days=1))


class GenerateIn(BaseModel):
    grade_level: str
    subject: str = "MATH"
    start_date: str  # YYYY-MM-DD


@router.post("/generate")
def generate_calendar(
    body: GenerateIn,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Lay out every topic's lessons across school days from a start date:
    one lesson per weekday, then a Review day and the Topic Assessment. Replaces
    any existing calendar for this grade + subject."""
    grade = body.grade_level
    subject = (body.subject or "MATH").upper()
    try:
        d = _weekday(date.fromisoformat(body.start_date))
    except ValueError:
        raise HTTPException(400, "start_date must be YYYY-MM-DD")

    db.query(CalendarEntry).filter(
        CalendarEntry.tenant_id == user.tenant_id,
        CalendarEntry.grade_level == grade,
        CalendarEntry.subject == subject).delete(synchronize_session=False)

    topics = (db.query(PacingTopic)
              .filter(PacingTopic.tenant_id == user.tenant_id,
                      PacingTopic.grade_level == grade,
                      PacingTopic.subject == subject)
              .order_by(PacingTopic.week_order).all())

    n = 0
    for t in topics:
        lessons = t.lessons or []
        if not lessons:
            db.add(CalendarEntry(
                tenant_id=user.tenant_id, grade_level=grade, subject=subject,
                date=d.isoformat(), topic_code=t.topic_code,
                title=f"{t.topic_code}: {t.name}", kind="lesson"))
            n += 1
            d = _next(d)
        for L in lessons:
            db.add(CalendarEntry(
                tenant_id=user.tenant_id, grade_level=grade, subject=subject,
                date=d.isoformat(), topic_code=t.topic_code,
                lesson_code=L.get("code", ""), title=L.get("title", ""),
                kind="lesson"))
            n += 1
            d = _next(d)
        db.add(CalendarEntry(
            tenant_id=user.tenant_id, grade_level=grade, subject=subject,
            date=d.isoformat(), topic_code=t.topic_code,
            title=f"{t.topic_code} Review", kind="review"))
        d = _next(d)
        db.add(CalendarEntry(
            tenant_id=user.tenant_id, grade_level=grade, subject=subject,
            date=d.isoformat(), topic_code=t.topic_code,
            title=f"{t.topic_code} Assessment", kind="assessment"))
        d = _next(d)

    db.commit()
    audit(db, actor=user, action="generate", entity_type="calendar",
          purpose="pacing_calendar")
    return {"created": n, "topics": len(topics),
            "start": body.start_date, "through": d.isoformat()}


@router.get("")
def get_calendar(
    grade: str = Query(...),
    subject: str = Query("MATH"),
    start: str = Query(""),
    end: str = Query(""),
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    q = db.query(CalendarEntry).filter(
        CalendarEntry.tenant_id == user.tenant_id,
        CalendarEntry.grade_level == grade,
        CalendarEntry.subject == (subject or "MATH").upper())
    if start:
        q = q.filter(CalendarEntry.date >= start)
    if end:
        q = q.filter(CalendarEntry.date <= end)
    entries = q.order_by(CalendarEntry.date).all()
    return {"entries": [
        {"id": e.id, "date": e.date, "topic_code": e.topic_code,
         "lesson_code": e.lesson_code, "title": e.title, "kind": e.kind,
         "note": e.note}
        for e in entries
    ]}


class EntryIn(BaseModel):
    grade_level: str
    subject: str = "MATH"
    date: str
    title: str
    topic_code: str = ""
    lesson_code: str = ""
    kind: str = "note"
    note: str = ""


@router.post("/entry")
def add_entry(
    body: EntryIn,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Add a single day entry (a note, a make-up day, a moved lesson…)."""
    try:
        date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")
    e = CalendarEntry(
        tenant_id=user.tenant_id, grade_level=body.grade_level,
        subject=(body.subject or "MATH").upper(), date=body.date,
        topic_code=body.topic_code, lesson_code=body.lesson_code,
        title=body.title, kind=body.kind or "note", note=body.note)
    db.add(e)
    db.commit()
    return {"id": e.id, "date": e.date, "title": e.title, "kind": e.kind}


@router.delete("/entry/{entry_id}")
def delete_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    e = db.get(CalendarEntry, entry_id)
    if not e or e.tenant_id != user.tenant_id:
        raise HTTPException(404, "Entry not found")
    db.delete(e)
    db.commit()
    return {"deleted": True}
