"""Coach section — collaborative planning: pacing calendar + PLC agendas."""
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from sqlalchemy.orm import Session

from pydantic import BaseModel

from app.ai import (
    ai_diagnostics,
    ask_assistant,
    generate_planning_guide,
    generate_plc_agenda,
    simplify_guide_text,
)
from app.export_docx import guide_to_docx
from app.db.session import get_db
from app.deps import audit, get_current_user
from app.models import (
    AppSetting,
    CalendarEntry,
    ClassRoom,
    CoachNote,
    CollabMeeting,
    District,
    FrameworkApplication,
    KeyDate,
    PacingTopic,
    PlanningDocument,
    PlcAgenda,
    SavedGuide,
    ScheduleBlock,
    School,
    StaffMember,
    Standard,
    Student,
    User,
)
from app.routers.pacing import _resolve_standards

router = APIRouter(prefix="/coach", tags=["coach"])

COACH_ROLES = {"reading_coach", "math_coach", "instructional_coach",
               "principal", "ap", "district_admin"}


def _require_coach(user: User = Depends(get_current_user)) -> User:
    if user.role not in COACH_ROLES:
        raise HTTPException(403, "Coach/leadership role required")
    return user


def _assessment_note(grade_level: str, topic_code: str) -> str:
    """A human 'administer by <date>' note from the district schedule, or ''."""
    from datetime import date as _date
    from app.assessment_schedule import lookup as _lookup
    row = _lookup(grade_level, topic_code)
    ab = (row or {}).get("administer_by")
    if not ab:
        return ""
    try:
        d = _date.fromisoformat(ab)
        return f"{topic_code} Assessment — administer by {d.strftime('%b %d, %Y')}"
    except ValueError:
        return ""


def _save_guide(db, user, grade_level, topic_code, subject, guide,
                status="ready") -> str:
    """Persist a generated guide so it survives navigating away."""
    rec = SavedGuide(
        tenant_id=user.tenant_id, grade_level=grade_level or "",
        topic_code=topic_code or "", subject=(subject or "MATH"),
        title=guide.get("title", "Planning Guide"), content=guide,
        ai_generated=bool(guide.get("ai_generated")), created_by=user.id,
        status=status)
    db.add(rec)
    db.commit()
    return rec.id


def _lesson_stubs(guide) -> list[dict]:
    """The lesson outline saved back onto a topic for the pacing calendar."""
    return [
        {"code": L.get("code", ""), "title": L.get("title", ""),
         "benchmarks": L.get("benchmarks", []), "focus": L.get("focus", "")}
        for L in (guide.get("lessons") or [])
    ]


def _run_pacing_guide_job(guide_id: str, text: str, benchmark_codes: list,
                          grade_level: str, subject: str, topic_name: str,
                          assessment_code: str, topic_id: str | None):
    """Generate a planning guide from pacing-guide text OUT OF BAND (several model
    calls, up to a couple of minutes) and write the result onto the pre-created
    SavedGuide, so the HTTP request that triggered it returns immediately. Runs in
    a threadpool with its own DB session."""
    from app.ai import generate_guide_from_pacing
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        standards = _resolve_standards(db, benchmark_codes) if benchmark_codes else []
        guide = generate_guide_from_pacing(
            text, standards, grade_level, subject or "MATH", topic_name)
        an = _assessment_note(grade_level, assessment_code)
        if an:
            guide.setdefault("quick_facts", {})["assessment_date"] = an
        if topic_id and guide.get("lessons"):
            topic = db.get(PacingTopic, topic_id)
            if topic:
                topic.lessons = _lesson_stubs(guide)
                db.add(topic)
        rec = db.get(SavedGuide, guide_id)
        if rec:
            rec.content = guide
            rec.title = guide.get("title", rec.title)
            rec.ai_generated = bool(guide.get("ai_generated"))
            rec.status = "ready"
            rec.error = ""
            db.add(rec)
        db.commit()
    except Exception as e:  # never let a background failure go silent
        db.rollback()
        rec = db.get(SavedGuide, guide_id)
        if rec:
            rec.status = "error"
            rec.error = f"{type(e).__name__}: {str(e)[:400]}"
            db.add(rec)
            db.commit()
    finally:
        db.close()


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


def _run_topic_guide_job(guide_id: str, topic_id: str):
    """Background generation for the topic-based guide (own DB session)."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        t = db.get(PacingTopic, topic_id)
        if not t:
            raise ValueError("Pacing topic not found")
        standards = _resolve_standards(db, t.benchmarks)
        topic_ctx = {
            "topic_code": t.topic_code, "chapter": t.chapter, "name": t.name,
            "grade_level": t.grade_level, "subject": t.subject, "quarter": t.quarter,
            "learning_target": t.learning_target,
            "success_criteria": t.success_criteria, "vocabulary": t.vocabulary,
            "time_frame": t.time_frame, "topic_focus": t.topic_focus,
            "ald_focus": t.ald_focus, "mtr_practices": t.mtr_practices,
            "materials": t.materials, "lessons": t.lessons,
            "assessment_date": _assessment_note(t.grade_level, t.topic_code),
        }
        guide = generate_planning_guide(topic_ctx, standards)
        rec = db.get(SavedGuide, guide_id)
        if rec:
            rec.content = guide
            rec.title = guide.get("title", rec.title)
            rec.ai_generated = bool(guide.get("ai_generated"))
            rec.status = "ready"
            rec.error = ""
            db.add(rec)
        db.commit()
    except Exception as e:
        db.rollback()
        rec = db.get(SavedGuide, guide_id)
        if rec:
            rec.status = "error"
            rec.error = f"{type(e).__name__}: {str(e)[:400]}"
            db.add(rec)
            db.commit()
    finally:
        db.close()


def _run_simplify_guide_job(guide_id: str):
    """Rewrite an existing guide's prose into plain language in place (own DB
    session). Keeps every problem, number and equation exactly as written."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        rec = db.get(SavedGuide, guide_id)
        if not rec:
            raise ValueError("Saved guide not found")
        new_guide, changed, err = simplify_guide_text(rec.content or {})
        if err and changed == 0:
            rec.status = "error"
            rec.error = err
            db.add(rec)
            db.commit()
            return
        rec.content = new_guide
        rec.status = "ready"
        rec.error = ""
        db.add(rec)
        db.commit()
    except Exception as e:
        db.rollback()
        rec = db.get(SavedGuide, guide_id)
        if rec:
            rec.status = "error"
            rec.error = f"{type(e).__name__}: {str(e)[:400]}"
            db.add(rec)
            db.commit()
    finally:
        db.close()


@router.post("/guide/{topic_id}")
def generate_guide(
    topic_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Generate a full lesson-by-lesson Collaborative Planning Guide for a topic,
    grounded in the pacing guide + B1G-M benchmark content. Runs in the
    BACKGROUND — returns a guide_id with status "generating"; poll the guide."""
    t = db.get(PacingTopic, topic_id)
    if not t:
        raise HTTPException(404, "Pacing topic not found")
    placeholder = {
        "title": f"Grade {t.grade_level} Collaborative Planning Guide — "
                 f"{t.topic_code}: {t.name}",
        "grade_level": t.grade_level, "subject": t.subject, "lessons": [],
        "ai_generated": False,
    }
    guide_id = _save_guide(db, user, t.grade_level, t.topic_code, t.subject,
                           placeholder, status="generating")
    background.add_task(_run_topic_guide_job, guide_id, t.id)
    audit(db, actor=user, action="generate", entity_type="planning_guide",
          entity_id=guide_id, purpose="collaborative_planning")
    return {"topic": t.name, "guide_id": guide_id, "status": "generating"}


@router.get("/ai-check")
def ai_check(user: User = Depends(_require_coach)):
    """Diagnose the AI configuration (used to troubleshoot guide generation)."""
    return ai_diagnostics()


class AssistantIn(BaseModel):
    message: str
    history: list[dict] = []


def _school_context(db: Session, user: User) -> dict:
    """A comprehensive, live snapshot of the whole system for the AI Coach —
    goal progress, per-teacher standing, pacing, saved guides, coaching notes,
    and upcoming key dates — so it can answer questions about what's actually
    happening. Student data stays aggregate/teacher-level (no student names)."""
    from datetime import date as _date
    from app.routers.reports import school_goal as _school_goal
    from app.routers.reports import teachers as _teachers_report

    tenant_id = user.tenant_id
    school = db.query(School).filter(School.tenant_id == tenant_id).first()
    students = db.query(Student).filter(Student.tenant_id == tenant_id).all()
    by_grade: dict[str, int] = {}
    for s in students:
        by_grade[s.grade_level] = by_grade.get(s.grade_level, 0) + 1
    topics = db.query(PacingTopic).filter(PacingTopic.tenant_id == tenant_id).all()

    goal = _school_goal(db=db, user=user)
    tr = _teachers_report(db=db, user=user)
    teachers_detail = [
        {"name": t["name"], "grades": t.get("grades", []),
         "students": t.get("students", 0), "pct_level_3_plus": t.get("pct_level_3_plus")}
        for t in tr.get("teachers", [])
    ]

    # Coaching notes / open follow-ups.
    notes = db.query(CoachNote).filter(CoachNote.tenant_id == tenant_id).all()
    tname = {u.id: u.name for u in db.query(User).filter(
        User.tenant_id == tenant_id).all()}
    today = _date.today().isoformat()
    open_followups = [
        {"teacher": tname.get(n.teacher_id, ""), "task": n.body,
         "due": n.due_date, "overdue": bool(n.due_date and n.due_date < today)}
        for n in notes if n.kind == "next_step" and not n.done]
    focus_areas = [
        {"teacher": tname.get(n.teacher_id, ""), "focus": n.body}
        for n in notes if n.kind == "focus"]

    # Saved planning guides by grade/topic.
    guides = db.query(SavedGuide).filter(SavedGuide.tenant_id == tenant_id).all()
    guides_by_grade: dict[str, int] = {}
    for g in guides:
        guides_by_grade[g.grade_level or "?"] = guides_by_grade.get(g.grade_level or "?", 0) + 1

    # Math + Math-DI schedule (from the master schedule), summarized per teacher.
    sched = _schedule_grouped(db, tenant_id)
    schedule_summary = []
    for grade, ts in sched.items():
        for t in ts:
            if not t.get("teaches_math"):
                continue
            math_times = sorted({f"{m['start']}-{m['end']}"
                                 for d in t["days"].values() for m in d["math"]})
            di_times = sorted({f"{x['start']}-{x['end']}"
                               for d in t["days"].values() for x in d["di"]})
            schedule_summary.append({
                "grade": grade, "room": t["room"], "teacher": t["teacher"],
                "program": t.get("program", ""),
                "math_times": math_times, "di_windows": di_times})
    # Per-grade planning windows (math planning where distinguishable).
    planning_by_grade: dict = {}
    for grade, ts in sched.items():
        wins = set()
        for t in ts:
            for d in t["days"].values():
                for p in d.get("planning", []):
                    if p.get("subject") in ("Planning", "Math CP"):
                        wins.add(f"{p['start']}-{p['end']} ({p['subject']})")
        if wins:
            planning_by_grade[grade] = sorted(wins)

    return {
        "school": school.name if school else "",
        "coach": user.name,
        "today": today,
        "students": len(students),
        "teachers": tr.get("diagnostics", {}).get("teachers_with_students", 0),
        "classes": tr.get("diagnostics", {}).get("total_classes", 0),
        "by_grade": dict(sorted(by_grade.items())),
        "goal_statement": goal.get("goal", ""),
        "goal_school_pct": goal.get("school", {}).get("goal_both_pct"),
        "goal_by_grade": {g: b.get("goal_both_pct") for g, b in goal.get("by_grade", {}).items()},
        "fast_math_by_grade": {
            g: b.get("fast_math", {}) for g, b in goal.get("by_grade", {}).items()},
        "iready_math_by_grade": {
            g: b.get("iready_math", {}) for g, b in goal.get("by_grade", {}).items()},
        "teachers_detail": teachers_detail,
        "open_followups": open_followups,
        "focus_areas": focus_areas,
        "pacing_topics": [f"G{t.grade_level} {t.topic_code} {t.name} "
                          f"({len(t.lessons or [])} lessons)" for t in topics],
        "saved_guides_by_grade": guides_by_grade,
        "standards_count": db.query(Standard).count(),
        "upcoming_dates": _upcoming_dates(db, tenant_id, within_days=60, limit=12),
        "math_schedule": schedule_summary,
        "planning_by_grade": planning_by_grade,
        "framework": _framework_context(),
        "framework_applications": [
            {"grade": a.grade, "topic": f"{a.topic_code}: {a.topic_name}",
             "component": a.component_name}
            for a in db.query(FrameworkApplication).filter(
                FrameworkApplication.tenant_id == tenant_id).all()],
        "collab_meetings": _collab_context(db, tenant_id),
        "goal_rubric": _goal_rubric_context(),
        "staff_directory": [
            {"section": s["section"], "grade": g, "program": s["program"] or "Gen Ed",
             "teacher": s["name"], "room": s["room"], "teaches_math": s["teaches_math"],
             "birthday": s["birthday"], "math_times": s.get("math_times", []),
             "di_windows": s.get("di_windows", [])}
            for g, ts in _staff_grouped(db, tenant_id).items() for s in ts],
    }


def _goal_rubric_context() -> dict:
    """The Math Goal Setting Rubric crosswalk (Level-3 thresholds) for the AI."""
    from app.goal_rubric import level3_thresholds
    return {"level3": level3_thresholds()}


def _ab_week(db, tenant_id) -> str:
    """Which A/B rotation side this week is. Uses the coach's anchor ('this week
    is A/B') when set, alternating weekly from it; else the calendar default."""
    from datetime import date, timedelta
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    s = db.query(AppSetting).filter(
        AppSetting.tenant_id == tenant_id, AppSetting.key == "ab_anchor").first()
    if s and s.value and s.value.get("date") and s.value.get("letter"):
        try:
            anchor = date.fromisoformat(s.value["date"])
            weeks = (monday - anchor).days // 7
            letter = s.value["letter"]
            return letter if weeks % 2 == 0 else ("B" if letter == "A" else "A")
        except Exception:
            pass
    from app.framework import current_ab_week
    return current_ab_week()


def _collab_context(db, tenant_id) -> dict:
    """This week's A/B collaborative-planning meetings for the AI snapshot."""
    cur = _ab_week(db, tenant_id)
    rows = db.query(CollabMeeting).filter(
        CollabMeeting.tenant_id == tenant_id, CollabMeeting.week == cur).all()
    meetings = [
        {"day": m.day, "time": m.time, "grade": m.grade, "group": m.group,
         "host": m.host}
        for m in sorted(rows, key=lambda x: (x.day, x.time))]
    return {"current_week": cur, "this_week": meetings}


def _framework_context() -> dict:
    """The Framework of Effective Instruction + this week's coaching lens, so the
    AI Coach can lead planning through it and elaborate as the expert."""
    from app.framework import load_framework, current_week_focus, planning_week_focus
    fw = load_framework()
    return {
        "this_week": current_week_focus(),
        "planning_for": planning_week_focus(),
        "components": [{"name": c["name"], "essence": c["essence"],
                        "in_math": c.get("in_math", "")}
                       for c in fw["components"]],
    }


@router.post("/assistant")
def assistant(
    body: AssistantIn,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """The in-system Expert AI Coach — grounded in the live system snapshot."""
    ctx = _school_context(db, user)
    result = ask_assistant(body.message, body.history, ctx)
    audit(db, actor=user, action="chat", entity_type="ai_assistant",
          purpose="coach_assistant")
    return result


@router.post("/guide/export/docx")
def export_guide_docx(
    guide: dict,
    user: User = Depends(_require_coach),
):
    """Render a (already-generated) planning guide to an editable Word document."""
    data = guide_to_docx(guide)
    fname = (guide.get("title", "planning-guide")
             .replace(" ", "_").replace("—", "-")[:80] + ".docx")
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# --- Topic management ---------------------------------------------------------

class NewTopicIn(BaseModel):
    grade_level: str
    subject: str = "MATH"
    topic_code: str
    name: str
    benchmarks: list[str] = []
    learning_target: str = ""
    quarter: str = ""


@router.post("/pacing")
def create_topic(
    body: NewTopicIn,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Create a new pacing topic (this year's planning week / folder). Generating
    a guide for it builds lessons from its benchmarks (B1G-M + ALDs); the AI
    designs the lesson sequence when the AI key is configured."""
    if not body.topic_code.strip() or not body.name.strip():
        raise HTTPException(400, "Topic code and name are required.")
    benchmarks = [b.strip().upper() for b in body.benchmarks if b.strip()]
    last = (db.query(PacingTopic)
            .filter(PacingTopic.tenant_id == user.tenant_id,
                    PacingTopic.grade_level == body.grade_level)
            .order_by(PacingTopic.week_order.desc()).first())
    t = PacingTopic(
        tenant_id=user.tenant_id, subject=(body.subject or "MATH").upper(),
        grade_level=body.grade_level, topic_code=body.topic_code.strip(),
        name=body.name.strip(), benchmarks=benchmarks,
        learning_target=body.learning_target.strip(),
        quarter=body.quarter.strip(), week_order=((last.week_order + 1) if last else 0),
        source="Coach-created", lessons=[],
    )
    db.add(t)
    db.commit()
    audit(db, actor=user, action="create", entity_type="pacing_topic",
          entity_id=t.id, purpose="planning_management")
    return {"id": t.id, "topic_code": t.topic_code, "name": t.name,
            "grade_level": t.grade_level, "benchmarks": benchmarks}


@router.get("/standards")
def list_grade_standards(
    grade: str = Query(...),
    subject: str = Query("MATH"),
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Benchmark codes available for a grade, to pick when creating a topic."""
    rows = db.query(Standard).filter(
        Standard.grade_level == grade,
        Standard.subject == subject.upper()).all()
    out = [{"code": s.code, "description": s.description,
            "has_ald": bool((s.details or {}).get("alds"))} for s in rows]
    out.sort(key=lambda x: x["code"])
    return {"grade": grade, "standards": out}


@router.post("/pacing/from-document")
async def pacing_from_document(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    grade_level: str = Form(...),
    subject: str = Form("MATH"),
    topic_name: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """One step: upload a topic's pacing guide -> create the topic (folder),
    store the file in it, and generate the Collaborative Planning Guide from the
    document's content. This is the primary 'upload a new topic' flow.

    The guide is written by several model calls, so generation runs in the
    BACKGROUND: this returns a guide_id with status "generating" right away and
    the page polls GET /coach/guides/{id} until it's ready."""
    import re as _re
    from app.doc_text import extract_document_text

    data = await file.read()
    if len(data) > _MAX_DOC_BYTES:
        raise HTTPException(400, "File is larger than the 25 MB limit.")
    text, reason = extract_document_text(file.filename, file.content_type, data)
    if not text:
        raise HTTPException(
            400, f"Could not read this document's text: {reason}. "
                 "Upload a text-based PDF, Word, or Excel pacing guide.")

    subject = (subject or "MATH").upper()
    # Grade: honor an explicit "Grade N / Grd N / GK" in the filename so a file
    # uploaded on the wrong tab still lands in the right grade.
    gm = _re.search(r"gr(?:a?de?)?\s*_?\s*(k|[0-8])(?![0-9])", file.filename, _re.I)
    if gm:
        g = gm.group(1).upper()
        grade_level = "K" if g == "K" else g

    # Name / code from the user's label or the filename. "Topic 1: Name" splits
    # cleanly; otherwise pull a clean "Topic N" / "Chapter N" (digits only, so
    # "_AIR" and other suffixes are not swept into the code).
    label = (topic_name or "").strip() or file.filename.rsplit(".", 1)[0]
    if ":" in label:
        code, name = [x.strip() for x in label.split(":", 1)]
    else:
        m = _re.search(r"(topic|chapter)\s*_?\s*(\d+)", label, _re.I)
        if m:
            code = f"{m.group(1).title()} {m.group(2)}"
            name = code
        else:
            code = name = _re.sub(r"[_\s]+", " ", label).strip()[:40]
    benchmarks = list(dict.fromkeys(_re.findall(r"MA\.\w+\.\w+\.\d+\.\d+", text)))

    last = (db.query(PacingTopic)
            .filter(PacingTopic.tenant_id == user.tenant_id,
                    PacingTopic.grade_level == grade_level)
            .order_by(PacingTopic.week_order.desc()).first())
    topic = PacingTopic(
        tenant_id=user.tenant_id, subject=subject,
        grade_level=grade_level, topic_code=code, name=name,
        benchmarks=benchmarks, learning_target="", quarter="",
        week_order=((last.week_order + 1) if last else 0),
        source="Uploaded pacing guide", lessons=[])
    db.add(topic)
    db.flush()

    doc = PlanningDocument(
        tenant_id=user.tenant_id, grade_level=grade_level, topic_code=code,
        subject=subject, name=file.filename, filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        size=len(data), data=data, uploaded_by=user.id)
    db.add(doc)
    db.commit()

    # Pre-create the guide record in "generating" state and hand the heavy work
    # to a background task — the request returns now instead of holding the
    # connection open through several model calls.
    placeholder = {
        "title": f"Grade {grade_level} Collaborative Planning Guide — {name}",
        "grade_level": grade_level, "subject": subject, "lessons": [],
        "ai_generated": False, "from_document": True,
    }
    guide_id = _save_guide(db, user, grade_level, code, subject, placeholder,
                           status="generating")
    background.add_task(_run_pacing_guide_job, guide_id, text, benchmarks,
                        grade_level, subject, name, code, topic.id)
    audit(db, actor=user, action="generate", entity_type="planning_guide",
          entity_id=guide_id, purpose="upload_pacing_and_generate")
    return {
        "topic": {"id": topic.id, "topic_code": code, "name": name,
                  "grade_level": grade_level},
        "guide_id": guide_id, "status": "generating", "document_id": doc.id,
        "benchmarks_detected": benchmarks,
    }


@router.post("/pacing/reload")
def reload_pacing(
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Restore the bundled standard pacing guides and standards (with ALDs) from
    the app's data files. Idempotent: updates existing topics/standards and adds
    any that are missing. Does NOT touch roster, students, or uploaded documents."""
    from app.seed import _load_math_standards, _load_pacing

    existing = {s.code for s in db.query(Standard).all()}
    n_std = _load_math_standards(db, existing)
    n_pac = _load_pacing(db, user.tenant_id)
    db.commit()
    total = db.query(PacingTopic).filter(
        PacingTopic.tenant_id == user.tenant_id).count()
    audit(db, actor=user, action="reload", entity_type="pacing",
          purpose="restore_pacing_guides")
    return {"reloaded": True, "standards_added": n_std,
            "pacing_added": n_pac, "topics_total": total}


class ClearIn(BaseModel):
    grade_level: str = ""


@router.post("/pacing/clear")
def clear_topics(
    body: ClearIn,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Full clean slate for a grade (or all grades when grade_level is blank):
    delete its pacing topics, agendas, calendar days, uploaded documents, and
    saved guides. The roster, students, and standards are untouched."""
    tq = db.query(PacingTopic).filter(PacingTopic.tenant_id == user.tenant_id)
    cq = db.query(CalendarEntry).filter(CalendarEntry.tenant_id == user.tenant_id)
    dq = db.query(PlanningDocument).filter(PlanningDocument.tenant_id == user.tenant_id)
    gq = db.query(SavedGuide).filter(SavedGuide.tenant_id == user.tenant_id)
    if body.grade_level:
        tq = tq.filter(PacingTopic.grade_level == body.grade_level)
        cq = cq.filter(CalendarEntry.grade_level == body.grade_level)
        dq = dq.filter(PlanningDocument.grade_level == body.grade_level)
        gq = gq.filter(SavedGuide.grade_level == body.grade_level)
    topic_ids = [t.id for t in tq.all()]
    if topic_ids:
        db.query(PlcAgenda).filter(
            PlcAgenda.pacing_topic_id.in_(topic_ids)).delete(synchronize_session=False)
    n = tq.delete(synchronize_session=False)
    cn = cq.delete(synchronize_session=False)
    dn = dq.delete(synchronize_session=False)
    gn = gq.delete(synchronize_session=False)
    db.commit()
    audit(db, actor=user, action="clear", entity_type="pacing_topic",
          purpose="planning_management")
    return {"topics_deleted": n, "calendar_entries_deleted": cn,
            "documents_deleted": dn, "guides_deleted": gn}


@router.delete("/pacing/{topic_id}")
def delete_pacing_topic(
    topic_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Delete a pacing topic (planning week) and its generated PLC agendas."""
    t = db.get(PacingTopic, topic_id)
    if not t or t.tenant_id != user.tenant_id:
        raise HTTPException(404, "Pacing topic not found")
    name = t.name
    db.query(PlcAgenda).filter(PlcAgenda.pacing_topic_id == t.id).delete(
        synchronize_session=False)
    db.delete(t)
    db.commit()
    audit(db, actor=user, action="delete", entity_type="pacing_topic",
          entity_id=topic_id, purpose="planning_management")
    return {"deleted": True, "name": name}


# --- Planning documents (grade / topic folders) -------------------------------

_MAX_DOC_BYTES = 25 * 1024 * 1024  # 25 MB per file


@router.get("/documents")
def list_documents(
    grade_level: str = Query(""),
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """List uploaded planning documents (metadata only), grouped by topic folder.
    Grade-level documents (no topic) land in the '_grade' folder."""
    q = db.query(PlanningDocument).filter(
        PlanningDocument.tenant_id == user.tenant_id)
    if grade_level:
        q = q.filter(PlanningDocument.grade_level == grade_level)
    folders: dict = {}
    for d in q.order_by(PlanningDocument.created_at.desc()).all():
        key = d.topic_code or "_grade"
        folders.setdefault(key, []).append({
            "id": d.id, "name": d.name, "filename": d.filename,
            "content_type": d.content_type, "size": d.size,
            "grade_level": d.grade_level, "topic_code": d.topic_code,
        })
    return {"grade_level": grade_level, "folders": folders}


@router.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    grade_level: str = Form(...),
    topic_code: str = Form(""),
    subject: str = Form("MATH"),
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Upload a document into a grade folder (optionally a topic sub-folder)."""
    data = await file.read()
    if len(data) > _MAX_DOC_BYTES:
        raise HTTPException(400, "File is larger than the 25 MB limit.")
    doc = PlanningDocument(
        tenant_id=user.tenant_id, grade_level=grade_level,
        topic_code=(topic_code or ""), subject=(subject or "MATH").upper(),
        name=file.filename, filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        size=len(data), data=data, uploaded_by=user.id,
    )
    db.add(doc)
    db.commit()
    audit(db, actor=user, action="upload", entity_type="planning_document",
          entity_id=doc.id, purpose="planning_resource_upload")
    return {"id": doc.id, "name": doc.name, "size": doc.size,
            "grade_level": grade_level, "topic_code": topic_code}


@router.get("/documents/{doc_id}/download")
def download_document(
    doc_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    d = db.get(PlanningDocument, doc_id)
    if not d or d.tenant_id != user.tenant_id:
        raise HTTPException(404, "Document not found")
    return Response(
        content=d.data, media_type=d.content_type,
        headers={"Content-Disposition": f'attachment; filename="{d.filename}"'},
    )


@router.post("/documents/{doc_id}/generate-guide")
def generate_guide_from_document(
    doc_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Read an uploaded pacing-guide document and generate the Collaborative
    Planning Guide from its content (grounded in the referenced B1G-M benchmarks
    + ALDs). Generation runs in the BACKGROUND — returns a guide_id with status
    "generating"; the page polls GET /coach/guides/{id}."""
    import re as _re
    from app.doc_text import extract_document_text

    d = db.get(PlanningDocument, doc_id)
    if not d or d.tenant_id != user.tenant_id:
        raise HTTPException(404, "Document not found")
    text, reason = extract_document_text(d.filename, d.content_type, d.data)
    if not text:
        raise HTTPException(
            400, f"Could not read this document's text: {reason}. "
                 "Upload a text-based PDF, Word, or Excel pacing guide.")

    # Benchmarks: any codes found in the document, plus the topic's benchmarks if
    # the document sits in a topic folder that exists.
    codes = list(dict.fromkeys(_re.findall(r"MA\.\w+\.\w+\.\d+\.\d+", text)))
    topic = None
    if d.topic_code:
        topic = db.query(PacingTopic).filter(
            PacingTopic.tenant_id == user.tenant_id,
            PacingTopic.topic_code == d.topic_code,
            PacingTopic.grade_level == d.grade_level).first()
        if topic and topic.benchmarks:
            for c in topic.benchmarks:
                if c not in codes:
                    codes.append(c)
    topic_name = (topic.name if topic else None) or d.topic_code or d.name.rsplit(".", 1)[0]

    placeholder = {
        "title": f"Grade {d.grade_level} Collaborative Planning Guide — {topic_name}",
        "grade_level": d.grade_level, "subject": d.subject or "MATH",
        "lessons": [], "ai_generated": False, "from_document": True,
    }
    guide_id = _save_guide(db, user, d.grade_level, d.topic_code, d.subject,
                           placeholder, status="generating")
    background.add_task(_run_pacing_guide_job, guide_id, text, codes,
                        d.grade_level, d.subject or "MATH", topic_name,
                        d.topic_code, topic.id if topic else None)
    audit(db, actor=user, action="generate", entity_type="planning_guide",
          entity_id=guide_id, purpose="guide_from_pacing_document")
    return {"topic": topic_name, "guide_id": guide_id, "status": "generating",
            "benchmarks_detected": codes, "chars_read": len(text)}


@router.delete("/documents/{doc_id}")
def delete_document(
    doc_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    d = db.get(PlanningDocument, doc_id)
    if not d or d.tenant_id != user.tenant_id:
        raise HTTPException(404, "Document not found")
    name = d.name
    db.delete(d)
    db.commit()
    audit(db, actor=user, action="delete", entity_type="planning_document",
          entity_id=doc_id, purpose="planning_management")
    return {"deleted": True, "name": name}


# --- Saved planning guides ----------------------------------------------------

@router.get("/guides")
def list_guides(
    grade_level: str = Query(""),
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """List saved planning guides (metadata), newest first, grouped by topic."""
    q = db.query(SavedGuide).filter(SavedGuide.tenant_id == user.tenant_id)
    if grade_level:
        q = q.filter(SavedGuide.grade_level == grade_level)
    folders: dict = {}
    for g in q.order_by(SavedGuide.created_at.desc()).all():
        key = g.topic_code or "_grade"
        folders.setdefault(key, []).append({
            "id": g.id, "title": g.title, "topic_code": g.topic_code,
            "grade_level": g.grade_level, "ai_generated": g.ai_generated,
            "created_at": g.created_at.isoformat() if g.created_at else "",
        })
    return {"grade_level": grade_level, "folders": folders}


@router.get("/guides/{guide_id}")
def get_guide(
    guide_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    g = db.get(SavedGuide, guide_id)
    if not g or g.tenant_id != user.tenant_id:
        raise HTTPException(404, "Saved guide not found")
    return {"id": g.id, "title": g.title, "guide": g.content,
            "status": g.status or "ready", "error": g.error or ""}


@router.delete("/guides/{guide_id}")
def delete_guide(
    guide_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    g = db.get(SavedGuide, guide_id)
    if not g or g.tenant_id != user.tenant_id:
        raise HTTPException(404, "Saved guide not found")
    title = g.title
    db.delete(g)
    db.commit()
    audit(db, actor=user, action="delete", entity_type="saved_guide",
          entity_id=guide_id, purpose="planning_management")
    return {"deleted": True, "title": title}


@router.post("/guides/{guide_id}/simplify")
def simplify_guide(
    guide_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Rewrite this saved guide's wording into plain, teacher-friendly language
    WITHOUT rebuilding it — problems, numbers and structure are untouched. Runs
    in the BACKGROUND: returns status "generating"; the page polls the guide."""
    g = db.get(SavedGuide, guide_id)
    if not g or g.tenant_id != user.tenant_id:
        raise HTTPException(404, "Saved guide not found")
    g.status = "generating"
    g.error = ""
    db.add(g)
    db.commit()
    background.add_task(_run_simplify_guide_job, guide_id)
    audit(db, actor=user, action="update", entity_type="saved_guide",
          entity_id=guide_id, purpose="simplify_language")
    return {"guide_id": guide_id, "status": "generating"}


# --- Coach Home (command center) + Teachers hub -------------------------------

@router.get("/home")
def coach_home(
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """The command-center landing: school-goal snapshot, teachers to watch
    (lowest % at Level 3+), open follow-ups (next-step notes), and quick counts.
    Composed from the existing reports so there is a single source of truth."""
    from datetime import date as _date
    from app.routers.reports import school_goal as _school_goal
    from app.routers.reports import teachers as _teachers_report

    goal = _school_goal(db=db, user=user)
    tr = _teachers_report(db=db, user=user)
    teachers = tr.get("teachers", [])
    # "Teachers to watch": those with data, lowest % Level 3+ first.
    with_data = [t for t in teachers if t.get("pct_level_3_plus") is not None]
    watch = sorted(with_data, key=lambda t: t["pct_level_3_plus"])[:6]

    # Open follow-ups (next steps not done), soonest due first.
    notes = db.query(CoachNote).filter(
        CoachNote.tenant_id == user.tenant_id,
        CoachNote.kind == "next_step",
        CoachNote.done == False).all()  # noqa: E712
    tname = {u.id: u.name for u in db.query(User).filter(
        User.tenant_id == user.tenant_id).all()}
    today = _date.today().isoformat()
    followups = sorted(
        [{"id": n.id, "teacher_id": n.teacher_id,
          "teacher": tname.get(n.teacher_id, ""), "body": n.body,
          "due_date": n.due_date, "overdue": bool(n.due_date and n.due_date < today)}
         for n in notes],
        key=lambda x: (x["due_date"] == "", x["due_date"]))

    from app.framework import current_week_focus, planning_week_focus
    return {
        "coach": {"name": user.name, "role": user.role},
        "today": today,
        "goal": goal,
        "teachers_to_watch": watch,
        "followups": followups,
        "this_week_lens": current_week_focus(),
        "planning_for": planning_week_focus(),
        "collab_meetings": _collab_context(db, user.tenant_id),
        "upcoming_dates": _upcoming_dates(db, user.tenant_id, within_days=45, limit=8),
        "upcoming_birthdays": _upcoming_birthdays(db, user.tenant_id, within_days=30, limit=10),
        "counts": {
            "teachers": tr.get("diagnostics", {}).get("teachers_with_students", 0),
            "students": db.query(Student).filter(
                Student.tenant_id == user.tenant_id).count(),
            "classes": tr.get("diagnostics", {}).get("total_classes", 0),
        },
    }


@router.get("/teacher/{teacher_id}/notes")
def list_teacher_notes(
    teacher_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Coach notes / focus areas / next steps for one teacher, newest first."""
    rows = db.query(CoachNote).filter(
        CoachNote.tenant_id == user.tenant_id,
        CoachNote.teacher_id == teacher_id).order_by(
        CoachNote.created_at.desc()).all()
    return {"notes": [
        {"id": n.id, "kind": n.kind, "body": n.body, "due_date": n.due_date,
         "done": n.done,
         "created_at": n.created_at.isoformat() if n.created_at else ""}
        for n in rows]}


class NoteIn(BaseModel):
    kind: str = "note"          # note | focus | next_step
    body: str
    due_date: str = ""


@router.post("/teacher/{teacher_id}/notes")
def add_teacher_note(
    teacher_id: str,
    payload: NoteIn,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    if not payload.body.strip():
        raise HTTPException(400, "Note text is required.")
    teacher = db.get(User, teacher_id)
    if not teacher or teacher.tenant_id != user.tenant_id:
        raise HTTPException(404, "Teacher not found")
    kind = payload.kind if payload.kind in ("note", "focus", "next_step") else "note"
    n = CoachNote(tenant_id=user.tenant_id, teacher_id=teacher_id,
                  author_id=user.id, kind=kind, body=payload.body.strip(),
                  due_date=payload.due_date or "")
    db.add(n)
    db.commit()
    return {"id": n.id, "kind": n.kind, "body": n.body, "due_date": n.due_date,
            "done": n.done,
            "created_at": n.created_at.isoformat() if n.created_at else ""}


@router.patch("/notes/{note_id}")
def toggle_note(
    note_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Mark a next-step follow-up done / not-done."""
    n = db.get(CoachNote, note_id)
    if not n or n.tenant_id != user.tenant_id:
        raise HTTPException(404, "Note not found")
    n.done = not n.done
    db.add(n)
    db.commit()
    return {"id": n.id, "done": n.done}


@router.delete("/notes/{note_id}")
def delete_note(
    note_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    n = db.get(CoachNote, note_id)
    if not n or n.tenant_id != user.tenant_id:
        raise HTTPException(404, "Note not found")
    db.delete(n)
    db.commit()
    return {"deleted": True}


# --- Key dates (school calendar the coach must stay ahead of) ------------------

def _date_row(d, today):
    """Serialize a KeyDate with a computed days-until for the active end of the
    event (a window is 'active/soon' until its end_date passes)."""
    from datetime import date as _date
    ref = d.end_date or d.date
    try:
        days = (_date.fromisoformat(d.date) - _date.fromisoformat(today)).days
        days_to_end = (_date.fromisoformat(ref) - _date.fromisoformat(today)).days
    except ValueError:
        days = days_to_end = None
    return {
        "id": d.id, "title": d.title, "category": d.category, "date": d.date,
        "end_date": d.end_date, "grade": d.grade, "note": d.note,
        "source": d.source, "days_until": days,
        "active": days_to_end is not None and days is not None
        and days <= 0 < days_to_end + 1,
    }


def _upcoming_dates(db, tenant_id, within_days=45, limit=8):
    """Dates whose window hasn't ended yet, soonest first, within a horizon."""
    from datetime import date as _date, timedelta
    today = _date.today()
    horizon = (today + timedelta(days=within_days)).isoformat()
    today_iso = today.isoformat()
    rows = db.query(KeyDate).filter(KeyDate.tenant_id == tenant_id).all()
    upcoming = []
    for d in rows:
        end = d.end_date or d.date
        if end >= today_iso and d.date <= horizon:
            upcoming.append(d)
    upcoming.sort(key=lambda d: d.date)
    return [_date_row(d, today_iso) for d in upcoming[:limit]]


def _upcoming_birthdays(db, tenant_id, within_days=30, limit=10):
    """Staff birthdays coming up within the horizon, soonest first. Birthdays
    are stored as 'M/D'; we compute the next occurrence from today (wrapping
    across the new year) so the Home page can celebrate them."""
    from datetime import date as _date, timedelta
    today = _date.today()
    out = []
    for s in db.query(StaffMember).filter(
            StaffMember.tenant_id == tenant_id, StaffMember.active == True).all():  # noqa: E712
        raw = (s.birthday or "").strip()
        if not raw or "/" not in raw:
            continue
        try:
            mo, da = [int(x) for x in raw.split("/")[:2]]
            year = today.year
            try:
                nxt = _date(year, mo, da)
            except ValueError:
                continue  # e.g. 2/29 in a non-leap year
            if nxt < today:
                try:
                    nxt = _date(year + 1, mo, da)
                except ValueError:
                    continue
        except Exception:
            continue
        days = (nxt - today).days
        if days <= within_days:
            out.append({
                "name": s.name, "section": s.section, "grade": s.grade,
                "program": s.program, "teaches_math": s.teaches_math,
                "date": f"{mo}/{da}", "days_until": days,
                "is_today": days == 0})
    out.sort(key=lambda x: x["days_until"])
    return out[:limit]


@router.get("/dates")
def list_key_dates(
    category: str = Query(""),
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """All key dates, chronological, with computed days-until."""
    from datetime import date as _date
    q = db.query(KeyDate).filter(KeyDate.tenant_id == user.tenant_id)
    if category:
        q = q.filter(KeyDate.category == category)
    rows = q.order_by(KeyDate.date).all()
    today = _date.today().isoformat()
    return {"dates": [_date_row(d, today) for d in rows]}


class KeyDateIn(BaseModel):
    title: str
    category: str = "custom"
    date: str
    end_date: str = ""
    grade: str = ""
    note: str = ""


@router.post("/dates")
def add_key_date(
    payload: KeyDateIn,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    if not payload.title.strip() or not payload.date:
        raise HTTPException(400, "A title and a date are required.")
    d = KeyDate(
        tenant_id=user.tenant_id, title=payload.title.strip(),
        category=payload.category or "custom", date=payload.date,
        end_date=payload.end_date or "", grade=payload.grade or "",
        note=payload.note or "", source="custom", created_by=user.id)
    db.add(d)
    db.commit()
    from datetime import date as _date
    return _date_row(d, _date.today().isoformat())


@router.delete("/dates/{date_id}")
def delete_key_date(
    date_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    d = db.get(KeyDate, date_id)
    if not d or d.tenant_id != user.tenant_id:
        raise HTTPException(404, "Date not found")
    db.delete(d)
    db.commit()
    return {"deleted": True}


@router.get("/guides/{guide_id}/summary")
def guide_coach_summary(
    guide_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """The Coach One-Pager for a saved guide: the essentials to present in
    planning, plus a short 'how to present it' narrative."""
    from app.coach_summary import build_coach_summary
    from app.ai import coach_one_pager_narrative

    g = db.get(SavedGuide, guide_id)
    if not g or g.tenant_id != user.tenant_id:
        raise HTTPException(404, "Saved guide not found")
    if (g.status or "ready") != "ready" or not (g.content or {}).get("lessons"):
        raise HTTPException(409, "This guide is still generating — try again in a moment.")
    summary = build_coach_summary(g.content)
    narrative = coach_one_pager_narrative(summary)
    lens = _guide_framework_lens(db, user.tenant_id, g.grade_level, g.topic_code)
    return {"id": g.id, "title": g.title, "summary": summary,
            "narrative": narrative, "framework_lens": lens}


def _guide_framework_lens(db, tenant_id, grade, topic_code) -> dict | None:
    """The most recent scripted framework application for this grade+topic, so
    the one-pager carries the week's coaching lens for the same content."""
    if not topic_code:
        return None
    r = (db.query(FrameworkApplication)
         .filter(FrameworkApplication.tenant_id == tenant_id,
                 FrameworkApplication.grade == grade,
                 FrameworkApplication.topic_code == topic_code)
         .order_by(FrameworkApplication.created_at.desc()).first())
    if not r:
        return None
    return {"component_name": r.component_name, "week_focus": r.week_focus,
            "content": r.content}


@router.get("/guides/{guide_id}/summary.docx")
def guide_coach_summary_docx(
    guide_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Download the Coach One-Pager as a printable Word document."""
    from app.coach_summary import build_coach_summary
    from app.ai import coach_one_pager_narrative
    from app.export_docx import coach_summary_to_docx

    g = db.get(SavedGuide, guide_id)
    if not g or g.tenant_id != user.tenant_id:
        raise HTTPException(404, "Saved guide not found")
    summary = build_coach_summary(g.content)
    narrative = coach_one_pager_narrative(summary)
    lens = _guide_framework_lens(db, user.tenant_id, g.grade_level, g.topic_code)
    data = coach_summary_to_docx(summary, narrative, lens)
    fname = f"CoachOnePager_{(g.topic_code or 'guide').replace(' ', '')}.docx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# --- Master schedule: math times & Math-DI windows ---------------------------

def _last_name(name: str) -> str:
    return (name or "").strip().split(" ")[-1].lower()


def _staff_index(db, tenant_id) -> tuple[dict, dict]:
    """Index the staff directory two ways so we can connect it to the master
    schedule: by teacher name (full + last), and by SECTION CODE. The code index
    matters because ASD rows on the master schedule carry the code (A13) as the
    'teacher', with no real name — this is how we resolve them to a person."""
    by_name: dict = {}
    by_section: dict = {}
    for s in db.query(StaffMember).filter(
            StaffMember.tenant_id == tenant_id, StaffMember.active == True).all():  # noqa: E712
        entry = {"section": s.section, "grade": s.grade, "program": s.program,
                 "name": s.name, "room": s.room, "role": s.role,
                 "teaches_math": s.teaches_math, "birthday": s.birthday}
        if s.name:
            by_name[s.name.lower()] = entry
            by_name.setdefault(_last_name(s.name), entry)
        if s.section:
            by_section[s.section.strip().upper()] = entry
    return by_name, by_section


def _resolve_teacher(raw: str, by_name: dict, by_section: dict) -> dict | None:
    """Match a master-schedule teacher label to a directory person — by full
    name, last name, or (for ASD rows) the section code it was stored under."""
    if not raw:
        return None
    return (by_name.get(raw.lower())
            or by_section.get(raw.strip().upper())
            or by_name.get(_last_name(raw)))


def _schedule_grouped(db, tenant_id) -> dict:
    """Rebuild the per-grade / per-teacher / per-day view from stored blocks."""
    from app.schedule_import import DAY_ORDER
    rows = db.query(ScheduleBlock).filter(
        ScheduleBlock.tenant_id == tenant_id).all()
    by_name, by_section = _staff_index(db, tenant_id)
    def _blank():
        return {"math": [], "di": [], "planning": []}
    teachers: dict = {}
    for b in rows:
        key = (b.grade, b.room, b.teacher_name)
        t = teachers.setdefault(key, {
            "grade": b.grade, "room": b.room, "teacher": b.teacher_name,
            "program": getattr(b, "program", "") or "",
            "days": {d: _blank() for d in DAY_ORDER}})
        day = t["days"].setdefault(b.day, _blank())
        if b.kind == "math":
            day["math"].append({"start": b.start_time, "end": b.end_time})
        elif b.kind == "planning":
            day.setdefault("planning", []).append(
                {"subject": b.subject, "start": b.start_time, "end": b.end_time})
        else:
            day["di"].append({"subject": b.subject, "start": b.start_time, "end": b.end_time})
    for t in teachers.values():
        for d in t["days"].values():
            for k in ("math", "di", "planning"):
                d.setdefault(k, []).sort(key=lambda x: x["start"])
        t["teaches_math"] = any(t["days"][d]["math"] for d in t["days"])
        # Connect this Math/DI row to the staff directory: stamp the section code
        # and, for ASD rows that carry the code as the 'teacher', resolve it to
        # the real person so the schedule, visit planner and host lists all show
        # a name instead of a bare code.
        raw = t["teacher"]
        match = _resolve_teacher(raw, by_name, by_section)
        t["code"] = raw.strip().upper() if raw.strip().upper() in by_section else ""
        t["section"] = (match["section"] if match else "") or t.get("code", "")
        if match:
            if match.get("name"):
                t["teacher"] = match["name"]
            if not t.get("program"):
                t["program"] = match.get("program", "")
            t["teaches_math"] = t["teaches_math"] or bool(match.get("teaches_math"))
            t["unmatched"] = False
        else:
            t["unmatched"] = True
    by_grade: dict = {}
    for t in sorted(teachers.values(), key=lambda x: (x["grade"], x["room"], x["teacher"])):
        by_grade.setdefault(t["grade"], []).append(t)
    return by_grade


# --- Staff / section directory ------------------------------------------------

def _schedule_conn(db, tenant_id) -> dict:
    """A lookup from the master schedule keyed by teacher name AND section code,
    giving each teacher's Math times and DI windows — so the Staff directory can
    show, per person, when they teach math and when they can run Math DI."""
    conn: dict = {}
    for grade, ts in _schedule_grouped(db, tenant_id).items():
        for t in ts:
            math_times = sorted({f"{m['start']}-{m['end']}"
                                 for d in t["days"].values() for m in d["math"]})
            di_windows = sorted({f"{x['start']}-{x['end']}"
                                 for d in t["days"].values() for x in d["di"]})
            info = {"math_times": math_times, "di_windows": di_windows}
            if t.get("teacher"):
                conn[t["teacher"].lower()] = info
            if t.get("section"):
                conn[t["section"].strip().upper()] = info
    return conn


def _staff_grouped(db, tenant_id) -> dict:
    """The staff directory grouped by grade, sections sorted, for the Staff page
    and the AI. Each row says whose class a code belongs to AND — connected to
    the master schedule — that teacher's Math time and DI window."""
    order = {"K": 0, "1": 1, "2": 2, "3": 3, "PK": 4, "VPK": 5}
    rows = db.query(StaffMember).filter(
        StaffMember.tenant_id == tenant_id, StaffMember.active == True).all()  # noqa: E712
    conn = _schedule_conn(db, tenant_id)
    by_grade: dict = {}
    for s in rows:
        sched = conn.get(s.name.lower()) or conn.get((s.section or "").strip().upper()) or {}
        by_grade.setdefault(s.grade, []).append({
            "section": s.section, "grade": s.grade, "program": s.program,
            "name": s.name, "room": s.room, "role": s.role,
            "teaches_math": s.teaches_math, "ext": s.ext, "birthday": s.birthday,
            "math_times": sched.get("math_times", []),
            "di_windows": sched.get("di_windows", []),
            "in_schedule": bool(sched)})
    for g in by_grade:
        by_grade[g].sort(key=lambda x: (x["program"], x["section"]))
    return dict(sorted(by_grade.items(), key=lambda kv: order.get(kv[0], 99)))


@router.post("/staff/import")
async def import_staff(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Upload the Staff Roster (.xlsx). Builds the section↔teacher directory
    (section code, grade, program, room, math role, birthday), replacing any
    previously imported staff for this school. Names live in the DB only."""
    from app.staff_import import parse_staff_roster

    data = await file.read()
    if len(data) > _MAX_DOC_BYTES:
        raise HTTPException(400, "File is larger than the 25 MB limit.")
    res = parse_staff_roster(data)
    if not res["staff"]:
        raise HTTPException(
            400, f"Could not read the roster: {res.get('reason')}. Upload the "
                 "Staff Roster .xlsx (with the CLASSROOM TEACHERS sheet).")
    db.query(StaffMember).filter(StaffMember.tenant_id == user.tenant_id).delete()
    math_n = 0
    for s in res["staff"]:
        if s["teaches_math"]:
            math_n += 1
        db.add(StaffMember(
            tenant_id=user.tenant_id, section=s["section"], grade=s["grade"],
            program=s["program"], name=s["name"], room=s["room"], role=s["role"],
            teaches_math=s["teaches_math"], ext=s["ext"], birthday=s["birthday"]))
    db.commit()
    audit(db, actor=user, action="import", entity_type="staff",
          purpose="staff_roster_import")
    return {"staff": len(res["staff"]), "math_teachers": math_n}


@router.get("/staff")
def get_staff(
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """The staff/section directory grouped by grade — whose class each code is."""
    by_grade = _staff_grouped(db, user.tenant_id)
    total = sum(len(v) for v in by_grade.values())
    return {"by_grade": by_grade, "total": total}


@router.post("/schedule/import")
async def import_schedule(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Upload the school master schedule (.xlsx). Parses each K-3 teacher's math
    times and their Science/Social-Studies (Math-DI) windows, replacing any
    previously imported schedule for this school."""
    from app.schedule_import import parse_master_schedule, to_blocks

    data = await file.read()
    if len(data) > _MAX_DOC_BYTES:
        raise HTTPException(400, "File is larger than the 25 MB limit.")
    res = parse_master_schedule(data)
    if not res["teachers"]:
        raise HTTPException(
            400, f"Could not read the schedule: {res.get('reason')}. Upload the "
                 "Avocado Master Schedule .xlsx (with the K-3 grade sheets).")
    db.query(ScheduleBlock).filter(
        ScheduleBlock.tenant_id == user.tenant_id).delete()
    n = 0
    for row in to_blocks(res["teachers"]):
        db.add(ScheduleBlock(
            tenant_id=user.tenant_id, grade=row["grade"], room=row["room"],
            program=row.get("program", ""), teacher_name=row["teacher"],
            day=row["day"], kind=row["kind"], subject=row["subject"],
            start_time=row["start"], end_time=row["end"]))
        n += 1
    db.commit()
    audit(db, actor=user, action="import", entity_type="schedule",
          purpose="master_schedule_import")
    math_teachers = sum(1 for t in res["teachers"] if t["teaches_math"])
    return {"teachers": len(res["teachers"]), "math_teachers": math_teachers,
            "blocks": n, "sheets": res["sheets_used"]}


@router.get("/schedule")
def get_schedule(
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """The parsed math + Math-DI schedule, grouped by grade and teacher."""
    return {"by_grade": _schedule_grouped(db, user.tenant_id)}


@router.get("/schedule/visit-plan")
def schedule_visit_plan(
    kind: str = Query("math"),
    minutes: int = Query(30),
    grade: str = Query(""),
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """A suggested conflict-free week: one visit per math teacher during a math
    block (kind=math) or their DI window (kind=di)."""
    from app.schedule_import import build_visit_plan
    if kind not in ("math", "di"):
        kind = "math"
    minutes = max(10, min(90, minutes))
    grouped = _schedule_grouped(db, user.tenant_id)
    plan = build_visit_plan(grouped, kind=kind, minutes=minutes, grade=grade or None)
    return {"kind": kind, "minutes": minutes, "grade": grade, "visits": plan}


@router.get("/framework")
def get_framework(
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """The Framework of Effective Instruction (6 components, expert elaboration),
    this week's coaching lens, and the year-long weekly focus plan."""
    from app.framework import (load_framework, current_week_focus,
                               planning_week_focus, WEEKLY_FOCUS)
    fw = load_framework()
    plan = [{"week": w, "component_key": k, "focus": f, "why": y}
            for (w, k, f, y) in WEEKLY_FOCUS]
    return {"framework": fw, "this_week": current_week_focus(),
            "planning_for": planning_week_focus(), "weekly_plan": plan}


# --- Collaborative planning (CPT) A/B rotation --------------------------------

def _collab_host_suggestions(db, tenant_id) -> dict:
    """Per grade, this year's math teachers split by Gen Ed / ASD — to assign a
    meeting host from real teachers instead of last year's names."""
    grouped = _schedule_grouped(db, tenant_id)
    out: dict = {}
    for grade, ts in grouped.items():
        gen = sorted({t["teacher"] for t in ts if t.get("teaches_math") and not t.get("program")})
        asd = sorted({t["teacher"] for t in ts if t.get("teaches_math") and t.get("program") == "ASD"})
        out[grade] = {"Gen Ed": gen, "ASD": asd}
    return out


@router.get("/collab")
def get_collab(
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """The math collaborative-planning A/B rotation, this week's A/B side, and
    host suggestions from this year's teachers."""
    rows = db.query(CollabMeeting).filter(
        CollabMeeting.tenant_id == user.tenant_id).all()
    by_week = {"A": [], "B": []}
    for m in sorted(rows, key=lambda x: (x.day, x.time)):
        by_week.setdefault(m.week, []).append({
            "id": m.id, "week": m.week, "day": m.day, "time": m.time,
            "grade": m.grade, "group": m.group, "host": m.host, "note": m.note})
    return {"by_week": by_week, "current_week": _ab_week(db, user.tenant_id),
            "suggestions": _collab_host_suggestions(db, user.tenant_id),
            "has_data": bool(rows)}


@router.post("/collab/set-week")
def set_ab_week(
    week: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Anchor the A/B rotation: 'this week is A' (or B). It alternates weekly."""
    from datetime import date, timedelta
    letter = "A" if str(week).upper().startswith("A") else "B"
    today = date.today()
    monday = (today - timedelta(days=today.weekday())).isoformat()
    s = db.query(AppSetting).filter(
        AppSetting.tenant_id == user.tenant_id, AppSetting.key == "ab_anchor").first()
    if not s:
        s = AppSetting(tenant_id=user.tenant_id, key="ab_anchor", value={})
        db.add(s)
    s.value = {"date": monday, "letter": letter}
    db.commit()
    return {"current_week": letter}


@router.post("/collab/load")
def load_collab(
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Load the standard A/B rotation template (times/grades/groups), replacing
    any existing meetings. Hosts start blank — assign this year's teachers."""
    import json as _json
    from pathlib import Path
    path = Path(__file__).parent.parent / "data" / "collab_planning.json"
    data = _json.loads(path.read_text())
    # This year's math teachers per grade — used to keep only host hints for
    # teachers who actually teach that grade this year (carry-overs).
    sugg = _collab_host_suggestions(db, user.tenant_id)

    def _valid_host(grade, hint):
        if not hint:
            return ""
        names = set((sugg.get(grade, {}).get("Gen Ed", [])) +
                    (sugg.get(grade, {}).get("ASD", [])))
        return hint if hint in names else ""

    db.query(CollabMeeting).filter(
        CollabMeeting.tenant_id == user.tenant_id).delete()
    n = 0
    filled = 0
    for m in data.get("meetings", []):
        host = _valid_host(m.get("grade", ""), m.get("host_hint", ""))
        if host:
            filled += 1
        db.add(CollabMeeting(
            tenant_id=user.tenant_id, week=m.get("week", "A"), day=m.get("day", ""),
            time=m.get("time", ""), grade=m.get("grade", ""), group=m.get("group", ""),
            host=host))
        n += 1
    db.commit()
    return {"loaded": n, "hosts_prefilled": filled}


class CollabIn(BaseModel):
    week: str = "A"
    day: str = ""
    time: str = ""
    grade: str = ""
    group: str = ""
    host: str = ""
    note: str = ""


@router.post("/collab")
def add_collab(payload: CollabIn, db: Session = Depends(get_db),
               user: User = Depends(_require_coach)):
    m = CollabMeeting(tenant_id=user.tenant_id, week=payload.week or "A",
                      day=payload.day, time=payload.time, grade=payload.grade,
                      group=payload.group, host=payload.host, note=payload.note)
    db.add(m)
    db.commit()
    return {"id": m.id}


@router.patch("/collab/{mid}")
def update_collab(mid: str, payload: CollabIn, db: Session = Depends(get_db),
                  user: User = Depends(_require_coach)):
    m = db.get(CollabMeeting, mid)
    if not m or m.tenant_id != user.tenant_id:
        raise HTTPException(404, "Meeting not found")
    for f in ("week", "day", "time", "grade", "group", "host", "note"):
        v = getattr(payload, f)
        if v is not None:
            setattr(m, f, v)
    db.add(m)
    db.commit()
    return {"id": m.id, "host": m.host}


@router.delete("/collab/{mid}")
def delete_collab(mid: str, db: Session = Depends(get_db),
                  user: User = Depends(_require_coach)):
    m = db.get(CollabMeeting, mid)
    if not m or m.tenant_id != user.tenant_id:
        raise HTTPException(404, "Meeting not found")
    db.delete(m)
    db.commit()
    return {"deleted": True}


# --- Framework applied to a specific grade + topic ---------------------------

class FrameworkTopicIn(BaseModel):
    grade: str
    topic_code: str
    component_key: str = ""   # blank -> use next week's (planning) lens


@router.post("/framework/for-topic")
def framework_for_topic(
    payload: FrameworkTopicIn,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Script how a framework component applies to a specific grade+topic, save
    it, and return it. Defaults to the week's planning lens if none given."""
    from app.framework import component_map, planning_week_focus
    from app.ai import generate_framework_application

    topic = db.query(PacingTopic).filter(
        PacingTopic.tenant_id == user.tenant_id,
        PacingTopic.grade_level == payload.grade,
        PacingTopic.topic_code == payload.topic_code).first()
    if not topic:
        raise HTTPException(404, "Topic not found for that grade.")

    comps = component_map()
    key = payload.component_key
    wf = planning_week_focus()
    if not key or key not in comps:
        key = wf["component_key"]
    component = comps.get(key, {})
    standards = _resolve_standards(db, topic.benchmarks) if topic.benchmarks else []

    content = generate_framework_application(
        component, payload.grade, f"{topic.topic_code}: {topic.name}",
        standards, wf["focus"])

    rec = FrameworkApplication(
        tenant_id=user.tenant_id, grade=payload.grade, topic_code=topic.topic_code,
        topic_name=topic.name, component_key=key,
        component_name=component.get("name", key), week_focus=wf["focus"],
        content=content, ai_generated=bool(content.get("ai_generated")),
        created_by=user.id)
    db.add(rec)
    db.commit()
    return {"id": rec.id, "grade": payload.grade, "topic_code": topic.topic_code,
            "topic_name": topic.name, "component_key": key,
            "component_name": component.get("name", key),
            "week_focus": wf["focus"], "content": content}


@router.get("/framework/applications")
def list_framework_applications(
    grade: str = Query(""),
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    q = db.query(FrameworkApplication).filter(
        FrameworkApplication.tenant_id == user.tenant_id)
    if grade:
        q = q.filter(FrameworkApplication.grade == grade)
    rows = q.order_by(FrameworkApplication.created_at.desc()).all()
    return {"applications": [
        {"id": r.id, "grade": r.grade, "topic_code": r.topic_code,
         "topic_name": r.topic_name, "component_key": r.component_key,
         "component_name": r.component_name, "week_focus": r.week_focus,
         "content": r.content, "ai_generated": r.ai_generated,
         "created_at": r.created_at.isoformat() if r.created_at else ""}
        for r in rows]}


@router.delete("/framework/applications/{app_id}")
def delete_framework_application(
    app_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    r = db.get(FrameworkApplication, app_id)
    if not r or r.tenant_id != user.tenant_id:
        raise HTTPException(404, "Not found")
    db.delete(r)
    db.commit()
    return {"deleted": True}
