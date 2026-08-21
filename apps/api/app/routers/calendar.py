"""Pacing calendar — day-by-day lesson schedule per grade, generated from the
topics' lesson sequences so coaches can track whether they're on pace."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.assessment_schedule import lookup as assessment_lookup
from app.assessment_schedule import schedule_for_grade
from app.db.session import get_db
from app.deps import audit, get_current_user
from app.models import CalendarEntry, District, PacingTopic, PlanningDocument, User

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
            # No lesson breakdown yet — reserve the topic's instructional span so
            # the calendar reflects real pacing. Estimate days from the time frame
            # (e.g. "~10 instructional days") or from the number of benchmarks.
            import re as _re
            m = _re.search(r"(\d+)", getattr(t, "time_frame", "") or "")
            days = int(m.group(1)) if m else max(4, len(t.benchmarks or []) * 3)
            for i in range(1, min(days, 20) + 1):
                db.add(CalendarEntry(
                    tenant_id=user.tenant_id, grade_level=grade, subject=subject,
                    date=d.isoformat(), topic_code=t.topic_code,
                    title=f"{t.topic_code} · Instructional Day {i}", kind="lesson",
                    note="Generate the planning guide to fill in the lessons."))
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
        # Anchor the Topic Assessment to the district's real "administer-by" date
        # when the schedule has it; otherwise place it sequentially.
        sched = assessment_lookup(grade, t.topic_code)
        adate = (sched or {}).get("administer_by")
        if adate:
            try:
                ad = date.fromisoformat(adate)
                assess_day = ad if ad >= d else d
            except ValueError:
                assess_day = d
        else:
            assess_day = d
        db.add(CalendarEntry(
            tenant_id=user.tenant_id, grade_level=grade, subject=subject,
            date=assess_day.isoformat(), topic_code=t.topic_code,
            title=f"{t.topic_code} Assessment", kind="assessment",
            note="District administer-by date" if adate else ""))
        d = _next(_weekday(assess_day))

    db.commit()
    audit(db, actor=user, action="generate", entity_type="calendar",
          purpose="pacing_calendar")
    return {"created": n, "topics": len(topics),
            "start": body.start_date, "through": d.isoformat()}


def _place_topic(db, user, grade, subject, t, d):
    """Lay one topic's lessons (one per weekday) + a Review day + the Topic
    Assessment starting at date d. Returns (entries_created, next_free_date)."""
    n = 0
    lessons = t.lessons or []
    if not lessons:
        import re as _re
        m = _re.search(r"(\d+)", getattr(t, "time_frame", "") or "")
        days = int(m.group(1)) if m else max(4, len(t.benchmarks or []) * 3)
        for i in range(1, min(days, 20) + 1):
            db.add(CalendarEntry(
                tenant_id=user.tenant_id, grade_level=grade, subject=subject,
                date=d.isoformat(), topic_code=t.topic_code,
                title=f"{t.topic_code} · Instructional Day {i}", kind="lesson",
                note="Generate the planning guide to fill in the lessons."))
            n += 1
            d = _next(d)
    for L in lessons:
        db.add(CalendarEntry(
            tenant_id=user.tenant_id, grade_level=grade, subject=subject,
            date=d.isoformat(), topic_code=t.topic_code,
            lesson_code=L.get("code", ""), title=L.get("title", ""), kind="lesson"))
        n += 1
        d = _next(d)
    db.add(CalendarEntry(
        tenant_id=user.tenant_id, grade_level=grade, subject=subject,
        date=d.isoformat(), topic_code=t.topic_code,
        title=f"{t.topic_code} Review", kind="review"))
    d = _next(d)
    sched = assessment_lookup(grade, t.topic_code)
    adate = (sched or {}).get("administer_by")
    assess_day = d
    if adate:
        try:
            ad = date.fromisoformat(adate)
            assess_day = ad if ad >= d else d
        except ValueError:
            assess_day = d
    db.add(CalendarEntry(
        tenant_id=user.tenant_id, grade_level=grade, subject=subject,
        date=assess_day.isoformat(), topic_code=t.topic_code,
        title=f"{t.topic_code} Assessment", kind="assessment",
        note="District administer-by date" if adate else ""))
    return n, _next(_weekday(assess_day))


class AppendIn(BaseModel):
    grade_level: str
    subject: str = "MATH"
    topic_code: str = ""    # which topic to place; blank = next unscheduled one
    start_date: str = ""    # fallback start when the calendar is still empty


@router.post("/append-topic")
def append_topic(
    body: AppendIn,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Continue the calendar: place ONE topic's lessons + review + assessment
    on the school days right AFTER the last scheduled day for this grade —
    without disturbing the topics already on the calendar. Use it after you add
    Topic 2, 3, … so the dates flow on from where the previous topic ended."""
    from sqlalchemy import func

    grade = body.grade_level
    subject = (body.subject or "MATH").upper()
    topics = (db.query(PacingTopic)
              .filter(PacingTopic.tenant_id == user.tenant_id,
                      PacingTopic.grade_level == grade,
                      PacingTopic.subject == subject)
              .order_by(PacingTopic.week_order).all())
    if not topics:
        raise HTTPException(404, "No topics for this grade yet — upload a pacing "
                                 "guide first.")
    scheduled = {c for (c,) in db.query(CalendarEntry.topic_code)
                 .filter(CalendarEntry.tenant_id == user.tenant_id,
                         CalendarEntry.grade_level == grade,
                         CalendarEntry.subject == subject).distinct()}
    if body.topic_code:
        t = next((x for x in topics if x.topic_code == body.topic_code), None)
        if not t:
            raise HTTPException(404, f"Topic {body.topic_code} not found.")
    else:
        t = next((x for x in topics if x.topic_code not in scheduled), None)
        if not t:
            raise HTTPException(400, "Every topic is already on the calendar. "
                                     "Pass a topic_code to re-place one.")

    # Start the school day after the last entry that ISN'T this topic's own, so a
    # re-run moves this topic cleanly to the end instead of after itself.
    last = (db.query(func.max(CalendarEntry.date))
            .filter(CalendarEntry.tenant_id == user.tenant_id,
                    CalendarEntry.grade_level == grade,
                    CalendarEntry.subject == subject,
                    CalendarEntry.topic_code != t.topic_code).scalar())
    if last:
        d = _next(date.fromisoformat(last))
    elif body.start_date:
        try:
            d = _weekday(date.fromisoformat(body.start_date))
        except ValueError:
            raise HTTPException(400, "start_date must be YYYY-MM-DD")
    else:
        raise HTTPException(400, "The calendar is empty — give a start_date for "
                                 "the first topic (later topics continue on their "
                                 "own).")

    # Clean re-run: clear this topic's own existing entries first.
    db.query(CalendarEntry).filter(
        CalendarEntry.tenant_id == user.tenant_id,
        CalendarEntry.grade_level == grade,
        CalendarEntry.subject == subject,
        CalendarEntry.topic_code == t.topic_code).delete(synchronize_session=False)

    first = d.isoformat()
    n, nxt = _place_topic(db, user, grade, subject, t, d)
    db.commit()
    audit(db, actor=user, action="append", entity_type="calendar",
          purpose="continue_pacing_calendar")
    return {"created": n, "topic": t.topic_code, "topic_name": t.name,
            "first": first, "through": (nxt - timedelta(days=1)).isoformat()}


class FromDocIn(BaseModel):
    year_start: int | None = None


@router.post("/from-document/{doc_id}")
def calendar_from_document(
    doc_id: str,
    body: FromDocIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Read the actual dates + lessons out of an uploaded pacing guide and put
    them on the calendar (e.g. 'Topic 1 begins August 13' → schedule from there).
    Replaces existing entries for that grade + topic."""
    from app.ai import parse_pacing_schedule
    from app.doc_text import extract_document_text

    d = db.get(PlanningDocument, doc_id)
    if not d or d.tenant_id != user.tenant_id:
        raise HTTPException(404, "Document not found")
    text, reason = extract_document_text(d.filename, d.content_type, d.data)
    if not text:
        raise HTTPException(400, f"Could not read the document: {reason}.")

    ys = (body.year_start if body and body.year_start else None)
    if not ys:
        today = date.today()
        ys = today.year if today.month >= 7 else today.year - 1

    entries, err = parse_pacing_schedule(text, ys)
    if not entries:
        raise HTTPException(
            400, err or "No dated schedule found in this pacing guide.")

    subject = (d.subject or "MATH").upper()
    db.query(CalendarEntry).filter(
        CalendarEntry.tenant_id == user.tenant_id,
        CalendarEntry.grade_level == d.grade_level,
        CalendarEntry.subject == subject,
        CalendarEntry.topic_code == d.topic_code).delete(synchronize_session=False)

    created = 0
    for e in entries:
        kind = e.get("kind", "lesson")
        if kind not in ("lesson", "review", "assessment", "note"):
            kind = "lesson"
        db.add(CalendarEntry(
            tenant_id=user.tenant_id, grade_level=d.grade_level, subject=subject,
            date=str(e.get("date", ""))[:10], topic_code=d.topic_code,
            lesson_code=str(e.get("lesson_code", ""))[:20],
            title=str(e.get("title", ""))[:200], kind=kind))
        created += 1
    db.commit()
    dates = sorted(str(e.get("date")) for e in entries)
    audit(db, actor=user, action="generate", entity_type="calendar",
          purpose="calendar_from_pacing_document")
    return {"created": created, "grade_level": d.grade_level,
            "first": dates[0], "last": dates[-1]}


@router.get("/assessment-schedule")
def assessment_schedule(
    grade: str = Query(...),
    user: User = Depends(_require_coach),
):
    """The district Topic Assessment Administration Schedule for a grade."""
    return {"grade": grade, "topics": schedule_for_grade(grade)}


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
