"""Coach section — collaborative planning: pacing calendar + PLC agendas."""
import io

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
    generate_di_packets,
    generate_planning_guide,
    generate_plc_agenda,
    generate_target_the_misses,
    simplify_guide_text,
)
from app.export_docx import guide_to_docx
from app.db.session import get_db
from app.deps import audit, get_current_user
from app.models import (
    AppSetting,
    AssessmentForm,
    AssessmentItem,
    CalendarEntry,
    ChatMessage,
    ClassRoom,
    CoachNote,
    CollabMeeting,
    DiPacket,
    District,
    Enrollment,
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
    StudentAssessment,
    TopicResult,
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
                          assessment_code: str, topic_id: str | None,
                          source_name: str = ""):
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
        # Record WHAT this guide was built from so a mismatch (wrong file/topic)
        # is visible on the guide itself.
        guide["source_document"] = source_name
        guide["source_benchmarks"] = list(benchmark_codes or [])
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
            # An empty guide (no lessons) means generation couldn't produce the
            # lesson-by-lesson content — surface WHY instead of a silent blank.
            if not guide.get("lessons"):
                rec.status = "error"
                rec.error = guide.get("ai_status") or (
                    "No lessons could be built from this document. Turn on the AI "
                    "key (AI_PROVIDER=anthropic, AI_API_KEY, AI_MODEL) so the guide "
                    "can be written from your pacing guide.")
            else:
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
            if not guide.get("lessons"):
                rec.status = "error"
                rec.error = guide.get("ai_status") or (
                    "No lessons on this topic yet. Turn on the AI key "
                    "(AI_PROVIDER=anthropic, AI_API_KEY, AI_MODEL), or upload the "
                    "topic's pacing guide and use 'Generate guide' on it.")
            else:
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
        "assessments": [
            {"grade": f.grade, "topic": f.topic_code, "test_name": f.test_name,
             "items": f.item_count, "points": f.total_points,
             "standards": f.standards or [],
             "results": _assessment_results_brief(db, f)}
            for f in db.query(AssessmentForm).filter(
                AssessmentForm.tenant_id == tenant_id).order_by(
                AssessmentForm.grade, AssessmentForm.topic_code).all()],
        "tier2_by_grade": _tier2_context(db),
    }


def _goal_rubric_context() -> dict:
    """The Math Goal Setting Rubric crosswalk (Level-3 thresholds) for the AI."""
    from app.goal_rubric import level3_thresholds
    return {"level3": level3_thresholds()}


def _tier2_context(db) -> dict:
    """Top Tier 2 academic words per K-3 grade (from the standards) for the AI."""
    from app.tier2_vocab import tier2_for_standards
    out = {}
    for g in ("K", "1", "2", "3"):
        words = tier2_for_standards(_standards_as_dicts(db, g))
        out[g] = [e["word"] for e in words[:14]]
    return out


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


_CHAT_HISTORY_TURNS = 40  # how many prior turns to feed the model


def _load_chat_history(db, user, limit=_CHAT_HISTORY_TURNS) -> list[dict]:
    """This coach's most recent conversation turns, oldest-first."""
    rows = (db.query(ChatMessage)
            .filter(ChatMessage.tenant_id == user.tenant_id,
                    ChatMessage.user_id == user.id)
            .order_by(ChatMessage.created_at.desc()).limit(limit).all())
    return [{"role": m.role, "content": m.content} for m in reversed(rows)]


@router.post("/assistant")
def assistant(
    body: AssistantIn,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """The in-system Expert AI Coach — grounded in the live system snapshot and
    the coach's OWN stored conversation history, so it remembers prior chats."""
    ctx = _school_context(db, user)
    # The database is the source of truth for history, so the AI remembers even
    # after a reload or a new session (the client-sent history is ignored).
    history = _load_chat_history(db, user)
    db.add(ChatMessage(tenant_id=user.tenant_id, user_id=user.id,
                       role="user", content=body.message))
    result = ask_assistant(body.message, history, ctx)
    db.add(ChatMessage(tenant_id=user.tenant_id, user_id=user.id,
                       role="assistant", content=result.get("reply", "")))
    db.commit()
    audit(db, actor=user, action="chat", entity_type="ai_assistant",
          purpose="coach_assistant")
    return result


@router.get("/assistant/history")
def assistant_history(
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Load this coach's saved AI-Coach conversation (for the page to restore)."""
    rows = (db.query(ChatMessage)
            .filter(ChatMessage.tenant_id == user.tenant_id,
                    ChatMessage.user_id == user.id)
            .order_by(ChatMessage.created_at).all())
    return {"messages": [{"role": m.role, "content": m.content} for m in rows]}


@router.delete("/assistant/history")
def clear_assistant_history(
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Clear this coach's saved AI-Coach conversation (start fresh)."""
    n = (db.query(ChatMessage)
         .filter(ChatMessage.tenant_id == user.tenant_id,
                 ChatMessage.user_id == user.id).delete())
    db.commit()
    audit(db, actor=user, action="delete", entity_type="ai_assistant",
          purpose="clear_chat_history")
    return {"cleared": n}


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
                        grade_level, subject, name, code, topic.id, file.filename)
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

_MAX_DOC_BYTES = 75 * 1024 * 1024  # 75 MB per file (fits a full textbook chapter)


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
                        d.topic_code, topic.id if topic else None, d.filename)
    audit(db, actor=user, action="generate", entity_type="planning_guide",
          entity_id=guide_id, purpose="guide_from_pacing_document")
    return {"topic": topic_name, "guide_id": guide_id, "status": "generating",
            "benchmarks_detected": codes, "chars_read": len(text)}


def _doc_role(filename: str, size: int, all_sizes: list) -> str:
    """Guess what a document is FOR so the AI knows how to use it in one guide.
    Filename wins (AIR = pacing guide, iPE = the book, B1G-M = the standards);
    size is the tie-breaker (the pacing guide is small, the textbook is huge)."""
    f = (filename or "").lower()
    if any(k in f for k in ("air", "pacing", "q1", "q2", "q3", "q4", "quarter", "scope")):
        return "PACING GUIDE (the day-by-day sequence and dates)"
    if any(k in f for k in ("ipe", "pupil", "textbook", "book", "student edition", "se_")):
        return "TEXTBOOK (the real lessons — page numbers, examples, practice)"
    if any(k in f for k in ("b1g", "big-m", "big_m", "bigm", "standard", "benchmark", "ald")):
        return "STANDARDS (B1G-M benchmarks and ALDs)"
    # No filename hint: the largest file in the folder is almost certainly the
    # textbook; a small one is the pacing guide.
    if all_sizes and size == max(all_sizes) and size > 2 * 1024 * 1024:
        return "TEXTBOOK (the real lessons — page numbers, examples, practice)"
    return "PACING GUIDE (the day-by-day sequence and dates)"


class _CombinedReq(BaseModel):
    grade_level: str
    topic_code: str
    subject: str = "MATH"


@router.post("/documents/generate-guide-combined")
def generate_guide_combined(
    req: _CombinedReq,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Generate ONE integrated planning guide from EVERY document in a topic
    folder — the pacing guide (AIR: sequence + dates), the textbook (iPE: real
    lessons, pages, examples) and any standards file — plus the topic's B1G-M
    benchmarks. Each document is labeled by its role so the AI weaves them into a
    single guide. Runs in the BACKGROUND; the page polls GET /coach/guides/{id}."""
    import re as _re
    from app.doc_text import extract_document_text

    docs = db.query(PlanningDocument).filter(
        PlanningDocument.tenant_id == user.tenant_id,
        PlanningDocument.grade_level == req.grade_level,
        PlanningDocument.topic_code == req.topic_code,
    ).order_by(PlanningDocument.size.asc()).all()
    if not docs:
        raise HTTPException(404, "No documents in this topic folder yet.")

    sizes = [d.size or 0 for d in docs]
    parts: list[str] = []
    codes: list[str] = []
    used: list[str] = []
    skipped: list[str] = []
    # Pacing guide first (short, holds the sequence), then standards, then the
    # book last (big, gets sliced by the model's window if needed).
    _order = {"PACING": 0, "STANDA": 1, "TEXTBO": 2}
    tagged = []
    for d in docs:
        role = _doc_role(d.filename, d.size or 0, sizes)
        tagged.append((_order.get(role[:6], 3), d, role))
    tagged.sort(key=lambda x: x[0])

    for _, d, role in tagged:
        text, reason = extract_document_text(d.filename, d.content_type, d.data)
        if not text:
            skipped.append(f"{d.filename} ({reason})")
            continue
        # The textbook is huge — keep a generous slice; the pacing guide/standards
        # are small and kept whole so the sequence and benchmarks are never lost.
        if role.startswith("TEXTBOOK") and len(text) > 120_000:
            text = text[:120_000]
        parts.append(f"===== {role} — {d.filename} =====\n{text}")
        used.append(d.filename)
        for c in _re.findall(r"MA\.\w+\.\w+\.\d+\.\d+", text):
            if c not in codes:
                codes.append(c)

    if not parts:
        raise HTTPException(
            400, "Could not read the text of any file in this folder. "
                 f"Skipped: {'; '.join(skipped)}. Upload text-based PDFs/Word/Excel.")

    combined = "\n\n".join(parts)

    topic = db.query(PacingTopic).filter(
        PacingTopic.tenant_id == user.tenant_id,
        PacingTopic.topic_code == req.topic_code,
        PacingTopic.grade_level == req.grade_level).first()
    if topic and topic.benchmarks:
        for c in topic.benchmarks:
            if c not in codes:
                codes.append(c)
    topic_name = (topic.name if topic else None) or req.topic_code

    placeholder = {
        "title": f"Grade {req.grade_level} Collaborative Planning Guide — {topic_name}",
        "grade_level": req.grade_level, "subject": (req.subject or "MATH").upper(),
        "lessons": [], "ai_generated": False, "from_document": True,
    }
    guide_id = _save_guide(db, user, req.grade_level, req.topic_code, req.subject,
                           placeholder, status="generating")
    source_name = " + ".join(used)
    background.add_task(_run_pacing_guide_job, guide_id, combined, codes,
                        req.grade_level, (req.subject or "MATH").upper(), topic_name,
                        req.topic_code, topic.id if topic else None, source_name)
    audit(db, actor=user, action="generate", entity_type="planning_guide",
          entity_id=guide_id, purpose="guide_from_combined_documents")
    return {"topic": topic_name, "guide_id": guide_id, "status": "generating",
            "files_used": used, "files_skipped": skipped,
            "benchmarks_detected": codes, "chars_read": len(combined)}


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


def _recover_stale_guide(db, g, minutes=25) -> None:
    """If a guide has been 'generating' far longer than any real run takes, the
    background job was lost (usually a server restart / redeploy mid-run). Flip
    it to error so the UI stops waiting and the coach can regenerate."""
    if (g.status or "ready") != "generating":
        return
    from datetime import datetime, timezone, timedelta
    started = g.updated_at or g.created_at
    if not started:
        return
    now = datetime.now(timezone.utc)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if now - started > timedelta(minutes=minutes):
        g.status = "error"
        g.error = ("Generation didn't finish — the server likely restarted while "
                   "it was running. Please click Generate again.")
        db.add(g)
        db.commit()


def _guard_ready(db, g) -> None:
    """Raise a clear error when a guide isn't a usable, ready guide (for the
    one-pager / template endpoints). Recovers stale 'generating' guides first."""
    _recover_stale_guide(db, g)
    status = g.status or "ready"
    if status == "error":
        raise HTTPException(400, g.error or "This guide failed to generate. "
                                            "Please generate it again.")
    if status == "generating":
        raise HTTPException(409, "This guide is still generating — try again in a "
                                 "moment.")
    if not (g.content or {}).get("lessons"):
        raise HTTPException(400, "This guide has no lessons yet — please generate "
                                 "it again (the AI must be on).")


@router.get("/guides/{guide_id}")
def get_guide(
    guide_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    g = db.get(SavedGuide, guide_id)
    if not g or g.tenant_id != user.tenant_id:
        raise HTTPException(404, "Saved guide not found")
    _recover_stale_guide(db, g)
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
        "results_focus": _home_results_focus(db, user.tenant_id),
        "counts": {
            "teachers": tr.get("diagnostics", {}).get("teachers_with_students", 0),
            "students": db.query(Student).filter(
                Student.tenant_id == user.tenant_id).count(),
            "classes": tr.get("diagnostics", {}).get("total_classes", 0),
        },
    }


@router.get("/teacher/{teacher_id}/hub")
def teacher_hub(
    teacher_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """The connected view for ONE teacher — pulls together their section code +
    Math/DI times (staff directory & schedule) and their class's topic-test
    results (average, weakest standard, most-missed) so the coach doesn't have
    to hop between Staff, Schedule and Assessments."""
    teacher = db.get(User, teacher_id)
    if not teacher or teacher.tenant_id != user.tenant_id:
        raise HTTPException(404, "Teacher not found")
    name = teacher.name or ""
    ln = _last_name(name)

    # Section + program + room (staff directory) and Math/DI times (schedule).
    by_name, by_section = _staff_index(db, user.tenant_id)
    staff = by_name.get(name.lower()) or by_name.get(ln)
    conn = _schedule_conn(db, user.tenant_id)
    sched = (conn.get(name.lower())
             or (conn.get((staff["section"] or "").strip().upper()) if staff else None)
             or {})

    # This teacher's class results across topic tests (matched by name).
    def _mine(tn: str) -> bool:
        tn = (tn or "").lower()
        return bool(tn) and (tn == name.lower() or _last_name(tn) == ln)

    form_ids = {r.form_id for r in db.query(TopicResult).filter(
        TopicResult.tenant_id == user.tenant_id).all() if _mine(r.teacher_name)}
    assessments = []
    for fid in form_ids:
        f = db.get(AssessmentForm, fid)
        if not f:
            continue
        a = _results_analysis(db, f)
        cls = next((c for c in a.get("classes", []) if _mine(c["teacher"])), None)
        if not cls:
            continue
        assessments.append({
            "form_id": f.id, "grade": f.grade, "topic": f.topic_code,
            "avg_percent": cls["avg_percent"], "color": cls["color"],
            "students": cls["students"],
            "weakest_standard": cls["by_standard"][0] if cls.get("by_standard") else None,
            "most_missed": cls.get("most_missed", [])[:4]})
    assessments.sort(key=lambda x: (x["grade"], x["topic"]))

    return {
        "teacher": {"id": teacher.id, "name": name},
        "staff": staff and {
            "section": staff.get("section"), "program": staff.get("program") or "Gen Ed",
            "room": staff.get("room"), "birthday": staff.get("birthday")},
        "schedule": {"math_times": sched.get("math_times", []),
                     "di_windows": sched.get("di_windows", [])},
        "assessments": assessments,
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
    _guard_ready(db, g)
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


def _build_template(db, g: SavedGuide) -> dict:
    """Assemble the teacher planning-template (walkout) for a saved guide:
    coach summary + Tier 2/3 vocabulary + the gradual-release scaffold."""
    from app.coach_summary import build_coach_summary
    from app.ai import classify_vocabulary
    from app.planning_template import build_planning_template

    from app.tier2_vocab import tier2_for_standards

    summary = build_coach_summary(g.content)
    standards = _resolve_standards(db, [b.get("code", "")
                                        for b in summary.get("benchmarks", [])])
    # _resolve_standards returns dicts (not ORM rows).
    std_ctx = [{"code": s.get("code", ""), "description": s.get("description", "")}
               for s in standards]
    # Tier 2 = the academic words mined from THIS topic's standards (the year's
    # focus). Tier 3 = the subject-specific words from the lesson vocabulary.
    # use_ai=False so this stays an instant Word download (no edge-proxy timeout).
    t2 = tier2_for_standards(standards)
    lesson_tiers = classify_vocabulary(summary.get("vocabulary", []), std_ctx,
                                       g.grade_level, use_ai=False)
    tiers = {
        "tier2": [{"word": e["word"], "meaning": e["meaning"],
                   "why": "appears in the test questions for "
                          + ", ".join(e["standards"][:3])} for e in t2],
        "tier3": lesson_tiers.get("tier3", []),
        "ai_generated": False,
    }
    return build_planning_template(g.content, summary, tiers)


@router.get("/guides/{guide_id}/template")
def guide_planning_template(
    guide_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """The teacher WALKOUT for a guide: a fillable gradual-release planning
    template with Tier 2 / Tier 3 vocabulary, so teachers internalize the guide
    by planning their own lesson in the same frame."""
    g = db.get(SavedGuide, guide_id)
    if not g or g.tenant_id != user.tenant_id:
        raise HTTPException(404, "Saved guide not found")
    _guard_ready(db, g)
    return {"id": g.id, "title": g.title, "template": _build_template(db, g)}


@router.get("/guides/{guide_id}/template.docx")
def guide_planning_template_docx(
    guide_id: str,
    example: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Download the teacher planning-template walkout as a fillable Word doc.
    Pass example=1 for a filled sample (cells worked from the guide)."""
    from app.export_docx import template_to_docx

    g = db.get(SavedGuide, guide_id)
    if not g or g.tenant_id != user.tenant_id:
        raise HTTPException(404, "Saved guide not found")
    _guard_ready(db, g)
    try:
        data = template_to_docx(_build_template(db, g), filled=example)
    except Exception as e:  # a data-shape issue shouldn't hang the download
        raise HTTPException(500, f"Could not build the template: "
                                 f"{type(e).__name__}: {str(e)[:200]}")
    suffix = "Example" if example else ""
    fname = f"PlanningTemplate{suffix}_{(g.topic_code or 'guide').replace(' ', '')}.docx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# --- Tier 2 academic vocabulary (this year's focus) ---------------------------

def _standards_as_dicts(db, grade: str) -> list[dict]:
    """All MATH standards for a grade as dicts (code + B1G-M details) for the
    Tier 2 miner."""
    rows = db.query(Standard).filter(
        Standard.subject == "MATH", Standard.grade_level == grade).all()
    return [{"code": s.code, "description": s.description, **(s.details or {})}
            for s in rows]


@router.get("/tier2")
def tier2_vocabulary(
    grade: str = Query(""),
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Tier 2 academic vocabulary mined from the STANDARDS, per grade — the
    cross-curricular words (determine, explain, justify …) that appear in the
    question stems. This year's focus; integrated into guides and templates."""
    from app.tier2_vocab import tier2_for_standards
    grades = [grade] if grade else ["K", "1", "2", "3"]
    out = {}
    for g in grades:
        out[g] = tier2_for_standards(_standards_as_dicts(db, g))
    return {"by_grade": out,
            "note": "Tier 2 = academic words used across every subject (the "
                    "school's focus this year). Tier 3 = subject-specific."}


# --- DI Focus: connect a weak standard to Tier 2, missed items & a reteach plan

def _aces_scaffold(desc: str, tier2: list[str]) -> list[dict]:
    """A plain-language ACES reteach scaffold for Red / Yellow / Green groups,
    weaving in the standard's Tier 2 academic words. Deterministic (instant)."""
    words = ", ".join(tier2[:5]) or "the academic words for this standard"
    return [
        {"tier": "Level 1 — Red", "color": "Red", "hex": "C0392B",
         "goal": "Build the idea from scratch with hands-on models.",
         "moves": [
             "I Do: model the skill with manipulatives (concrete) and think aloud "
             "using the words " + words + ".",
             "We Do: do 2-3 together, students copy each step on whiteboards.",
             "Post a sentence frame with the Tier 2 words and have every student "
             "say it.",
             "Keep numbers small; check after every step."]},
        {"tier": "Level 2 — Yellow", "color": "Yellow", "hex": "F1C40F",
         "goal": "Move from pictures to numbers with guided practice.",
         "moves": [
             "Connect concrete → pictorial → abstract for the same problem.",
             "Guided practice with CUBS on a word problem; students explain using "
             + words + ".",
             "Partner practice (Rally Coach), then a quick check."]},
        {"tier": "Level 3+ — Green (enrichment)", "color": "Green", "hex": "27AE60",
         "goal": "Deepen and extend — reason and justify.",
         "moves": [
             "Multi-step / word problems at or above grade level.",
             "Students justify and explain their reasoning out loud and in writing, "
             "using " + words + ".",
             "Extension: create their own problem for a partner to solve."]},
    ]


@router.get("/di-focus")
def di_focus(
    grade: str = Query(...),
    standard: str = Query(...),
    form_id: str = Query(""),
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Everything to plan DI for ONE weak standard, in one place: the standard's
    description + Level-3 ALD, its Tier 2 academic words, the most-missed
    questions on it, and a Red/Yellow/Green ACES reteach scaffold."""
    from app.tier2_vocab import tier2_for_standards

    sd = _resolve_standards(db, [standard])
    s = sd[0] if sd else {"code": standard, "description": ""}
    tier2 = [e["word"] for e in tier2_for_standards([s])]
    ald3 = (s.get("alds") or {}).get("level3", "")

    # Most-missed questions on this standard (a specific test, or across the grade).
    missed: list = []
    forms = db.query(AssessmentForm).filter(
        AssessmentForm.tenant_id == user.tenant_id,
        AssessmentForm.grade == grade)
    if form_id:
        forms = forms.filter(AssessmentForm.id == form_id)
    for f in forms.all():
        a = _results_analysis(db, f)
        for m in a.get("most_missed", []):
            if m.get("standard") == standard:
                missed.append({**m, "topic": f.topic_code})
    missed.sort(key=lambda m: -m.get("miss_pct", 0))

    return {
        "grade": grade,
        "standard": {"code": s.get("code", standard),
                     "description": s.get("description", ""),
                     "ald_level3": ald3,
                     "clarifications": s.get("clarifications", [])[:3]},
        "tier2": tier2,
        "most_missed": missed[:6],
        "scaffold": _aces_scaffold(s.get("description", ""), tier2),
    }


# --- DI packets: three rotation tiers grounded in the B1G-M standard ---------

# The school's DI Rotation Chart: score band -> tier, and the 7-day station
# rotation (i-Ready / TLC teacher-led / IXL-Skill Trainer-Independent Practice /
# OPM / Data Chat). tlc_sessions = how many teacher-led touches that tier gets,
# which drives how many scripted reteach sessions its packet carries.
_DI_ROTATION = [
    {"name": "Intensive", "stars": 1, "band": "0-49%", "lo": 0, "hi": 50,
     "tlc_sessions": 2,
     "rotation": ["i-Ready", "TLC", "IXL/Skill Trainer/Independent Practice",
                  "i-Ready", "TLC", "OPM", "Data Chat"]},
    {"name": "Cusp", "stars": 2, "band": "50-68%", "lo": 50, "hi": 69,
     "tlc_sessions": 2,
     "rotation": ["TLC", "IXL/Skill Trainer/Independent Practice", "i-Ready",
                  "TLC", "IXL/Skill Trainer/Independent Practice", "OPM", "Data Chat"]},
    {"name": "Strategic", "stars": 3, "band": "69-100%", "lo": 69, "hi": 100,
     "tlc_sessions": 1,
     "rotation": ["IXL/Skill Trainer/Independent Practice", "i-Ready", "TLC",
                  "IXL/Skill Trainer/Independent Practice", "i-Ready", "OPM", "Data Chat"]},
]


def _di_tier_for(pct: float):
    for t in _DI_ROTATION:
        if t["lo"] <= pct < t["hi"] or (t["hi"] == 100 and pct >= 100):
            return t
    return _DI_ROTATION[-1] if pct >= 69 else _DI_ROTATION[0]


def _teachers_list(teacher: str) -> list:
    """A DI packet's teacher field can be one class or a comma-joined GROUP of
    classes that share the same deficiency (one packet for all of them)."""
    return [t.strip() for t in (teacher or "").split(",") if t.strip()]


# A class whose evidence-backed weakest standard is at/above this % is treated
# as proficient — enrichment, not reteach.
_DI_PROFICIENT_CUT = 85.0
# Standards assessed by this many questions or fewer are "thin evidence" and are
# not used as a DI target on their own (they can still show, flagged ⚠).
_DI_MIN_QUESTIONS = 2


def _di_target(by_standard: list) -> dict:
    """The evidence-backed DI target for a class: the WEAKEST standard assessed by
    at least _DI_MIN_QUESTIONS questions (a 1-question standard's % is too noisy to
    prescribe on). Marks needs_di False when even that weakest is at proficiency."""
    ranked = sorted((s for s in by_standard if s.get("percent") is not None),
                    key=lambda s: s["percent"])
    solid = [s for s in ranked if (s.get("questions") or 0) >= _DI_MIN_QUESTIONS]
    pick = solid[0] if solid else (ranked[0] if ranked else None)
    if not pick:
        return {"standard": "", "percent": None, "needs_di": False, "note": ""}
    note = ""
    if not solid:
        note = "thin evidence (few questions) — confirm with i-Ready/FAST"
    needs = pick["percent"] < _DI_PROFICIENT_CUT
    if not needs:
        note = f"already proficient ({pick['percent']}%) — enrichment, not reteach"
    return {"standard": pick["standard"], "percent": pick["percent"],
            "needs_di": needs, "note": note}


def _di_grouping(db, f: AssessmentForm) -> list:
    """Recommend which classes can SHARE one DI packet vs. need their own, by
    comparing what each class actually missed. Classes with the same weakest
    benchmark AND overlapping most-missed questions are grouped — so the coach
    generates one packet for the group instead of three identical ones.
    Deterministic (no AI / no tokens)."""
    a = _results_analysis(db, f)
    reteach, enrichment, unmatched = [], [], []
    for c in a.get("classes", []):
        prof = {"teacher": c["teacher"],
                # Use the EVIDENCE-BACKED target (weakest standard with >=2
                # questions), not a 1-question artifact.
                "standard": c.get("di_target", ""),
                "missed": {m["position"] for m in (c.get("most_missed") or [])[:4]},
                "avg": c.get("avg_percent"), "students": c.get("students", 0),
                "red": c.get("red_on_target", 0),
                "yellow": c.get("yellow_on_target", 0)}
        if not c.get("teacher") or c["teacher"] == "—":
            unmatched.append(prof)          # students whose class didn't match roster
        elif not c.get("needs_di", True):
            enrichment.append(prof)         # every kid Green on the weakest — enrichment
        else:
            reteach.append(prof)            # has Red/Yellow — tiered reteach packet

    clusters, used = [], set()
    for i, p in enumerate(reteach):
        if p["teacher"] in used:
            continue
        group = [p]
        used.add(p["teacher"])
        for q in reteach[i + 1:]:
            if q["teacher"] in used:
                continue
            if q["standard"] and q["standard"] == p["standard"] \
                    and len(p["missed"] & q["missed"]) >= 2:
                group.append(q)
                used.add(q["teacher"])
        shared = (sorted(set.intersection(*[g["missed"] for g in group]))
                  if len(group) > 1 else sorted(group[0]["missed"]))
        clusters.append({
            "kind": "share" if len(group) > 1 else "own",
            "standard": p["standard"],
            "teachers": [g["teacher"] for g in group],
            "class_count": len(group),
            "students": sum(g["students"] for g in group),
            "red": sum(g.get("red", 0) for g in group),
            "yellow": sum(g.get("yellow", 0) for g in group),
            "shared_questions": [f"Q{n}" for n in shared],
            "shared": len(group) > 1,
        })
    clusters.sort(key=lambda c: -c["class_count"])
    if enrichment:
        clusters.append({
            "kind": "enrichment", "standard": "",
            "teachers": [g["teacher"] for g in enrichment],
            "class_count": len(enrichment),
            "students": sum(g["students"] for g in enrichment),
            "shared_questions": [], "shared": False})
    if unmatched:
        clusters.append({
            "kind": "unmatched", "standard": "",
            "teachers": ["Unmatched students (fix roster)"],
            "class_count": len(unmatched),
            "students": sum(g["students"] for g in unmatched),
            "shared_questions": [], "shared": False})
    return clusters


def _class_missed_on_standard(db, f: AssessmentForm, standard: str,
                              teacher: str = "") -> list:
    """Most-missed questions on ONE benchmark, for ONE class (teacher) or grade-wide
    when teacher is empty. Ranked by how many students missed each item, with the
    correct answer and captured question text so DI targets that group's misses."""
    q = db.query(TopicResult).filter(TopicResult.form_id == f.id)
    tl = _teachers_list(teacher)
    if tl:
        q = q.filter(TopicResult.teacher_name.in_(tl))
    rows = q.all()
    items = {it.position: it for it in db.query(AssessmentItem).filter(
        AssessmentItem.form_id == f.id).all()}
    n = len(rows)
    cnt: dict = {}
    for r in rows:
        for pos in (r.missed_positions or []):
            it = items.get(pos)
            if it and it.standard == standard:
                cnt[pos] = cnt.get(pos, 0) + 1
    out = []
    for pos, c in cnt.items():
        it = items[pos]
        out.append({"position": pos, "missed": c,
                    "miss_pct": round(100.0 * c / n, 1) if n else 0,
                    "standard": standard, "correct_response": it.correct_response,
                    "stem": (it.stem or "")[:300]})
    return sorted(out, key=lambda m: -m["missed"])


def _class_top_missed(db, f: AssessmentForm, teacher: str = "", limit: int = 8) -> list:
    """The class's (or grade's) most-missed questions ACROSS ALL standards — so the
    'Fix the Misses' page can also target questions that fall outside the packet's
    reteach standard. Ranked by how many students missed each item."""
    q = db.query(TopicResult).filter(TopicResult.form_id == f.id)
    tl = _teachers_list(teacher)
    if tl:
        q = q.filter(TopicResult.teacher_name.in_(tl))
    rows = q.all()
    items = {it.position: it for it in db.query(AssessmentItem).filter(
        AssessmentItem.form_id == f.id).all()}
    n = len(rows)
    cnt: dict = {}
    for r in rows:
        for pos in (r.missed_positions or []):
            cnt[pos] = cnt.get(pos, 0) + 1
    out = []
    for pos, c in cnt.items():
        it = items.get(pos)
        if not it:
            continue
        out.append({"position": pos, "missed": c,
                    "miss_pct": round(100.0 * c / n, 1) if n else 0,
                    "standard": it.standard, "correct_response": it.correct_response,
                    "stem": (it.stem or "")[:300]})
    return sorted(out, key=lambda m: -m["missed"])[:limit]


def _di_students_by_tier(db, f: AssessmentForm, standard: str,
                         teacher: str = "") -> dict:
    """Group this test's students into the three rotation tiers by their score ON
    THE CHOSEN STANDARD (falling back to their overall topic %), so each packet
    lists exactly who is in it and how big each group is. Scoped to ONE class when
    teacher is given, else grade-wide."""
    groups = {t["name"]: [] for t in _DI_ROTATION}
    q = db.query(TopicResult).filter(TopicResult.form_id == f.id)
    tl = _teachers_list(teacher)
    if tl:
        q = q.filter(TopicResult.teacher_name.in_(tl))
    for r in q.all():
        by = (r.by_standard or {}).get(standard)
        if by and by.get("possible"):
            pct = round(100.0 * by.get("earned", 0.0) / by["possible"], 1)
        else:
            pct = r.percent
        t = _di_tier_for(pct)
        groups[t["name"]].append({
            "student_name": r.student_name, "student_id": r.student_id,
            "teacher": r.teacher_name, "percent": pct})
    for v in groups.values():
        v.sort(key=lambda x: x["percent"])
    return groups


def _run_di_packet_job(packet_id: str, grade: str, standard: str, form_id: str,
                       teacher: str = ""):
    """Background generation of the three-tier DI packet (own DB session). When
    teacher is set, everything (most-missed + tier groups) is scoped to THAT
    class, so each teacher gets a packet for their own class's deficiencies."""
    from app.db.session import SessionLocal
    from app.tier2_vocab import tier2_for_standards

    db = SessionLocal()
    try:
        rec = db.get(DiPacket, packet_id)
        if not rec:
            return
        sd = _resolve_standards(db, [standard])
        s = sd[0] if sd else {"code": standard, "description": ""}
        tier2 = [e["word"] for e in tier2_for_standards([s])]

        # Most-missed questions on this standard, scoped to the class (or grade).
        missed = []
        f = db.get(AssessmentForm, form_id) if form_id else None
        forms = [f] if f else db.query(AssessmentForm).filter(
            AssessmentForm.tenant_id == rec.tenant_id,
            AssessmentForm.grade == grade).all()
        for form in [x for x in forms if x]:
            missed.extend(_class_missed_on_standard(db, form, standard, teacher))
        missed.sort(key=lambda m: -m.get("miss_pct", 0))

        packet = generate_di_packets(s, missed, grade, _DI_ROTATION, tier2)
        packet["test_items"] = missed[:8]  # show which missed questions we reteach
        packet["teacher"] = teacher
        # Layer 2: target the class's most-missed questions ACROSS ALL standards
        # (only forms that exist), so the 'Fix the Misses' page also hits questions
        # outside the packet's reteach standard.
        all_missed = []
        for form in [x for x in forms if x]:
            all_missed.extend(_class_top_missed(db, form, teacher, limit=8))
        all_missed.sort(key=lambda m: -m.get("missed", 0))
        packet["target_the_misses"] = generate_target_the_misses(
            s, all_missed[:8], grade, packet.get("model", "none"))
        packet["stems_captured"] = any((m.get("stem") or "").strip() for m in all_missed)

        # Attach the student groups (who is in each tier + counts), scoped to class.
        groups = _di_students_by_tier(db, f, standard, teacher) if f else {}
        for t in packet.get("tiers", []):
            g = groups.get(t.get("tier"), [])
            t["students"] = g
            t["student_count"] = len(g)
        packet["groups_total"] = sum(len(v) for v in groups.values()) if groups else 0

        rec.content = packet
        rec.ai_generated = bool(packet.get("ai_generated"))
        if not packet.get("tiers"):
            rec.status = "error"
            rec.error = packet.get("ai_status") or "No packets could be generated."
        else:
            rec.status = "ready"
            rec.error = ""
        db.add(rec)
        db.commit()
    except Exception as e:
        db.rollback()
        rec = db.get(DiPacket, packet_id)
        if rec:
            rec.status = "error"
            rec.error = f"{type(e).__name__}: {str(e)[:300]}"
            db.add(rec)
            db.commit()
    finally:
        db.close()


class _DiPacketReq(BaseModel):
    grade: str
    standard: str
    form_id: str = ""
    teacher: str = ""  # "" = grade-wide; else target this class's deficiencies


@router.get("/di-grouping")
def di_grouping(
    form_id: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Recommend which classes can share ONE DI packet vs. need their own, from
    what each class actually missed on this test. Saves generating duplicates."""
    f = db.get(AssessmentForm, form_id)
    if not f or f.tenant_id != user.tenant_id:
        raise HTTPException(404, "Assessment not found")
    return {"grade": f.grade, "form_id": f.id, "clusters": _di_grouping(db, f)}


@router.post("/di-packets")
def create_di_packets(
    req: _DiPacketReq,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Start background generation of the three-tier DI packet for one benchmark,
    grade-wide or for a single class (teacher). Returns a packet_id to poll."""
    scope = f" · {req.teacher}" if req.teacher else ""
    rec = DiPacket(
        tenant_id=user.tenant_id, grade_level=req.grade, standard=req.standard,
        form_id=req.form_id, teacher=req.teacher, created_by=user.id,
        status="generating",
        title=f"DI Packets — Grade {req.grade} · {req.standard}{scope}",
        content={"standard": req.standard, "grade_level": req.grade,
                 "teacher": req.teacher, "tiers": []})
    db.add(rec)
    db.commit()
    background.add_task(_run_di_packet_job, rec.id, req.grade, req.standard,
                        req.form_id, req.teacher)
    audit(db, actor=user, action="generate", entity_type="di_packet",
          entity_id=rec.id, purpose="di_packets")
    return {"packet_id": rec.id, "status": "generating"}


@router.get("/di-packets/{packet_id}")
def get_di_packets(
    packet_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    rec = db.get(DiPacket, packet_id)
    if not rec or rec.tenant_id != user.tenant_id:
        raise HTTPException(404, "DI packet not found")
    _recover_stale_guide(db, rec, minutes=15)
    return {"id": rec.id, "status": rec.status, "error": rec.error,
            "title": rec.title, "ai_generated": rec.ai_generated,
            "content": rec.content}


@router.get("/di-packets/{packet_id}/html")
def di_packets_html(
    packet_id: str,
    dl: int = Query(0),
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """The printable student packet — visual models drawn per benchmark. Opened
    in a new tab and printed straight from the browser; with dl=1 it downloads as
    a self-contained .html file (open it, then print or Save as PDF)."""
    from app.export_html import render_di_packet_html
    rec = db.get(DiPacket, packet_id)
    if not rec or rec.tenant_id != user.tenant_id:
        raise HTTPException(404, "DI packet not found")
    if rec.status != "ready":
        raise HTTPException(409, "Packets are not ready yet.")
    headers = {}
    if dl:
        fn = f"DI-Packet-G{rec.grade_level}-{rec.standard}.html"
        headers["Content-Disposition"] = f'attachment; filename="{fn}"'
    return Response(content=render_di_packet_html(rec.content),
                    media_type="text/html", headers=headers)


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


# --- Topic-test blueprints & standards-assessed tracking ----------------------

def _form_summary(db, form: AssessmentForm) -> dict:
    """One form's standards breakdown (items + points per standard)."""
    items = db.query(AssessmentItem).filter(
        AssessmentItem.form_id == form.id).order_by(AssessmentItem.position).all()
    per_std: dict = {}
    for it in items:
        if not it.standard:
            continue
        e = per_std.setdefault(it.standard, {"standard": it.standard,
                                             "items": 0, "points": 0.0,
                                             "positions": []})
        e["items"] += 1
        e["points"] += it.points
        e["positions"].append(it.position)
    return {
        "id": form.id, "test_name": form.test_name, "test_id": form.test_id,
        "grade": form.grade, "topic_code": form.topic_code,
        "subject": form.subject, "item_count": form.item_count,
        "total_points": form.total_points, "standards": form.standards or [],
        "by_standard": sorted(per_std.values(), key=lambda x: -x["points"]),
    }


def _std_desc_map(db) -> dict:
    """code -> short standard description, to label the standards we track."""
    out: dict = {}
    for s in db.query(Standard).all():
        out[s.code] = s.description
    return out


@router.post("/assessments/import")
async def import_assessment(
    answer_key: UploadFile = File(...),
    test: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Upload a topic-test ANSWER KEY (PDF) — and optionally the test PDF — to
    register the blueprint: the standard each item assesses, the key and points.
    Re-uploading the same Test Id replaces it. This is what we track all year."""
    from app.assessment_import import parse_answer_key, parse_test_questions

    ak = await answer_key.read()
    if len(ak) > _MAX_DOC_BYTES:
        raise HTTPException(400, "Answer key is larger than the 25 MB limit.")
    res = parse_answer_key(ak)
    if not res["items"]:
        raise HTTPException(
            400, f"Could not read the answer key: {res.get('reason')}. Upload the "
                 "answer-key PDF (the item/standard/answer table).")

    stems: dict = {}
    if test is not None:
        tb = await test.read()
        if len(tb) <= _MAX_DOC_BYTES:
            stems = parse_test_questions(tb).get("questions", {})

    # Replace any existing form with the same Test Id (or name) for this tenant.
    q = db.query(AssessmentForm).filter(AssessmentForm.tenant_id == user.tenant_id)
    existing = None
    if res["test_id"]:
        existing = q.filter(AssessmentForm.test_id == res["test_id"]).first()
    if not existing and res["test_name"]:
        existing = q.filter(AssessmentForm.test_name == res["test_name"]).first()
    if existing:
        db.query(AssessmentItem).filter(
            AssessmentItem.form_id == existing.id).delete()
        db.delete(existing)
        db.flush()

    form = AssessmentForm(
        tenant_id=user.tenant_id, test_name=res["test_name"],
        test_id=res["test_id"], grade=res["grade"], topic_code=res["topic_code"],
        subject=res["subject"], item_count=res["item_count"],
        total_points=res["total_points"], standards=res["standards"],
        created_by=user.id)
    db.add(form)
    db.flush()
    for it in res["items"]:
        db.add(AssessmentItem(
            tenant_id=user.tenant_id, form_id=form.id, position=it["position"],
            item_id=it["item_id"], standard=it["standard"],
            standard_raw=it["standard_raw"], correct_response=it["correct_response"],
            points=it["points"], scored=it["scored"],
            stem=str(stems.get(it["position"], ""))[:2000]))
    db.commit()
    audit(db, actor=user, action="import", entity_type="assessment_form",
          entity_id=form.id, purpose="topic_test_blueprint")
    return {"form": _form_summary(db, form),
            "questions_captured": len(stems)}


@router.get("/assessments")
def list_assessments(
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """All topic-test blueprints grouped by grade, plus the year-long map of
    standards assessed per grade (how many tests/items touch each standard)."""
    forms = db.query(AssessmentForm).filter(
        AssessmentForm.tenant_id == user.tenant_id).all()
    order = {"K": 0, "1": 1, "2": 2, "3": 3, "4": 4}
    by_grade: dict = {}
    for f in forms:
        by_grade.setdefault(f.grade, []).append(_form_summary(db, f))
    for g in by_grade:
        by_grade[g].sort(key=lambda x: x["topic_code"])

    desc = _std_desc_map(db)
    coverage: dict = {}
    for g, summaries in by_grade.items():
        std_map: dict = {}
        for s in summaries:
            for bs in s["by_standard"]:
                e = std_map.setdefault(bs["standard"], {
                    "standard": bs["standard"],
                    "description": desc.get(bs["standard"], ""),
                    "items": 0, "points": 0.0, "topics": []})
                e["items"] += bs["items"]
                e["points"] += bs["points"]
                e["topics"].append(s["topic_code"])
        coverage[g] = sorted(std_map.values(), key=lambda x: x["standard"])
    return {
        "by_grade": dict(sorted(by_grade.items(), key=lambda kv: order.get(kv[0], 99))),
        "coverage": dict(sorted(coverage.items(), key=lambda kv: order.get(kv[0], 99))),
        "total_forms": len(forms),
    }


@router.get("/assessments/{form_id}")
def get_assessment(
    form_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """One blueprint with every item (position, standard, answer, points, stem)."""
    f = db.get(AssessmentForm, form_id)
    if not f or f.tenant_id != user.tenant_id:
        raise HTTPException(404, "Assessment not found")
    items = db.query(AssessmentItem).filter(
        AssessmentItem.form_id == f.id).order_by(AssessmentItem.position).all()
    desc = _std_desc_map(db)
    return {
        "form": _form_summary(db, f),
        "items": [{"position": it.position, "item_id": it.item_id,
                   "standard": it.standard,
                   "standard_desc": desc.get(it.standard, ""),
                   "correct_response": it.correct_response, "points": it.points,
                   "scored": it.scored, "stem": it.stem} for it in items],
    }


@router.delete("/assessments/{form_id}")
def delete_assessment(
    form_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    f = db.get(AssessmentForm, form_id)
    if not f or f.tenant_id != user.tenant_id:
        raise HTTPException(404, "Assessment not found")
    db.query(AssessmentItem).filter(AssessmentItem.form_id == f.id).delete()
    name = f.test_name
    db.delete(f)
    db.commit()
    audit(db, actor=user, action="delete", entity_type="assessment_form",
          entity_id=form_id, purpose="assessment_management")
    return {"deleted": True, "test_name": name}


# --- Topic-test RESULTS: score, color-code, most-missed, per class/student ----

def _color_for(grade: str, pct: float | None) -> dict:
    """Level (1-5) + color name/hex for a percent, via the Math Goal rubric."""
    from app.goal_rubric import topic_color
    tc = topic_color(grade, pct) if pct is not None else None
    return tc or {"level": 0, "color": "", "hex": ""}


@router.post("/assessments/{form_id}/results")
async def import_results(
    form_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Upload a grade-wide RESULTS spreadsheet (one row per student, one column
    per question) for this topic test. Scores each student against the answer
    key, color-codes by the Math Goal rubric, and stores per student/class.
    Re-uploading replaces the results for this test."""
    from app.topic_results_import import parse_results

    f = db.get(AssessmentForm, form_id)
    if not f or f.tenant_id != user.tenant_id:
        raise HTTPException(404, "Assessment not found")
    data = await file.read()
    if len(data) > _MAX_DOC_BYTES:
        raise HTTPException(400, "File is larger than the 25 MB limit.")
    items = [{"position": it.position, "item_id": it.item_id,
              "standard": it.standard, "correct_response": it.correct_response,
              "points": it.points, "scored": it.scored}
             for it in db.query(AssessmentItem).filter(
                 AssessmentItem.form_id == f.id).all()]
    res = parse_results(data, items)
    if not res["rows"]:
        raise HTTPException(
            400, f"Could not read the results: {res.get('reason')}. Upload the "
                 "grade Excel with a Student column and one column per question "
                 "(Q1, Q2 …).")
    # If the export carries no teacher/class column, recover each student's
    # teacher from the roster so per-class results and DI packets still work.
    _fill_teacher_from_roster(db, user.tenant_id, res["rows"])
    db.query(TopicResult).filter(TopicResult.form_id == f.id).delete()
    for r in res["rows"]:
        pct = r["percent"]
        lvl = _color_for(f.grade, pct)["level"]
        db.add(TopicResult(
            tenant_id=user.tenant_id, form_id=f.id, grade=f.grade,
            teacher_name=r["teacher_name"], student_id=r["student_id"],
            student_name=r["student_name"], points_earned=r["points_earned"],
            points_possible=r["points_possible"], percent=pct, level=lvl,
            by_standard=r["by_standard"], missed_positions=r["missed_positions"]))
    # Connect the results to the rest of the system: write each student's topic %
    # into StudentAssessment so it flows into Reports and Goal Analysis next to
    # their FAST/i-Ready (matched to a roster student by ID, then by name).
    linked = _link_topic_results_to_students(db, user.tenant_id, f, res["rows"])
    db.commit()
    audit(db, actor=user, action="import", entity_type="topic_results",
          entity_id=f.id, purpose="topic_test_results")
    classes = sorted({r["teacher_name"] for r in res["rows"] if r["teacher_name"]})
    return {"students": len(res["rows"]), "classes": classes,
            "linked_to_roster": linked,
            "questions_matched": res.get("detected", {}).get("questions_matched", 0)}


def _topic_period(topic_code: str) -> str:
    """'Topic 1' -> 'TP1'. The period key Reports/Analysis read topic scores by."""
    import re as _re
    m = _re.search(r"(\d+)", topic_code or "")
    return f"TP{m.group(1)}" if m else (topic_code or "TP").replace(" ", "").upper()


def _student_teacher_map(db, tenant_id) -> dict:
    """student.id -> teacher display name, from the roster (Enrollment ->
    ClassRoom -> teacher User). Prefers the student's MATH class, then homeroom,
    then any class, so a topic-test result lands under the right teacher."""
    q = (db.query(Enrollment, ClassRoom, User)
         .join(ClassRoom, Enrollment.class_id == ClassRoom.id)
         .join(User, ClassRoom.teacher_id == User.id)
         .filter(ClassRoom.tenant_id == tenant_id))
    rank = {"MATH": 0, "HOMEROOM": 1}
    best: dict = {}
    for en, cls, tch in q.all():
        r = rank.get((cls.subject or "").upper(), 2)
        name = (tch.name or "").strip() or (cls.name or "").strip()
        if not name:
            continue
        cur = best.get(en.student_id)
        if cur is None or r < cur[0]:
            best[en.student_id] = (r, name)
    return {sid: v[1] for sid, v in best.items()}


def _name_key(name: str) -> str:
    """An order- and punctuation-insensitive key for matching a results name to
    the roster: lowercase, letters only, drop single-letter middle initials, and
    sort the tokens — so 'ABSALON, MILANI', 'Milani Absalon' and 'Milani A Absalon'
    all collapse to the same key."""
    import re as _re
    toks = [t for t in _re.sub(r"[^a-z ]", " ", (name or "").lower()).split()
            if len(t) > 1]
    return " ".join(sorted(toks))


def _fill_teacher_from_roster(db, tenant_id, rows) -> int:
    """When the results file has no teacher/class column, look each student up in
    the roster (by district id, then by name) and fill their teacher, so the
    per-class breakdown and DI packets still work. Mutates rows; returns how many
    teachers were filled."""
    if not rows or all((r.get("teacher_name") or "").strip() for r in rows):
        return 0
    students = db.query(Student).filter(Student.tenant_id == tenant_id).all()
    by_did = {(s.district_student_id or "").strip(): s
              for s in students if s.district_student_id}
    by_name = {}
    for s in students:
        full = f"{s.first_name} {s.last_name}"
        by_name[full.strip().lower()] = s
        by_name.setdefault(f"{s.last_name} {s.first_name}".strip().lower(), s)
        by_name.setdefault(_name_key(full), s)  # order/punctuation-insensitive
    tmap = _student_teacher_map(db, tenant_id)
    filled = 0
    for r in rows:
        if (r.get("teacher_name") or "").strip():
            continue
        stu = by_did.get((r.get("student_id") or "").strip())
        if not stu:
            raw = r.get("student_name") or ""
            nm = " ".join(raw.replace(",", " ").split()).lower()
            stu = by_name.get(nm) or by_name.get(_name_key(raw))
        if stu and tmap.get(stu.id):
            r["teacher_name"] = tmap[stu.id]
            filled += 1
    return filled


def _link_topic_results_to_students(db, tenant_id, f: AssessmentForm, rows) -> int:
    """Upsert a StudentAssessment (source=TOPIC) per matched roster student so a
    topic test's percents appear in Reports and Goal Analysis. Match by district
    student id, then by full name. Percent is stored as a 0-1 fraction (the shape
    Reports expects). Returns how many were linked."""
    students = db.query(Student).filter(Student.tenant_id == tenant_id).all()
    by_did = {(s.district_student_id or "").strip(): s for s in students if s.district_student_id}
    by_name = {}
    for s in students:
        by_name[f"{s.first_name} {s.last_name}".strip().lower()] = s
        by_name.setdefault(f"{s.last_name} {s.first_name}".strip().lower(), s)
    period = _topic_period(f.topic_code)
    subject = (f.subject or "MATH").upper()
    n = 0
    for r in rows:
        stu = by_did.get((r.get("student_id") or "").strip())
        if not stu:
            # Names may arrive as "Last, First" (Performance Matters) — drop the
            # comma so it matches the roster's "last first" key.
            nm = (r.get("student_name") or "").replace(",", " ")
            nm = " ".join(nm.split()).lower()
            stu = by_name.get(nm)
        if not stu:
            continue
        frac = round(r["percent"] / 100.0, 4)
        existing = db.query(StudentAssessment).filter(
            StudentAssessment.tenant_id == tenant_id,
            StudentAssessment.student_id == stu.id,
            StudentAssessment.source == "TOPIC",
            StudentAssessment.subject == subject,
            StudentAssessment.period == period).first()
        if existing:
            existing.percent = frac
            existing.label = f.topic_code
            db.add(existing)
        else:
            db.add(StudentAssessment(
                tenant_id=tenant_id, student_id=stu.id, source="TOPIC",
                subject=subject, period=period, percent=frac, label=f.topic_code))
        n += 1
    return n


def _results_analysis(db, f: AssessmentForm) -> dict:
    """Class averages, per-standard mastery, and most-missed questions — grade
    wide and by class — all color-coded, from stored TopicResult rows."""
    rows = db.query(TopicResult).filter(TopicResult.form_id == f.id).all()
    if not rows:
        return {"students": 0, "classes": [], "by_standard": [],
                "most_missed": [], "students_list": []}
    items = {it.position: it for it in db.query(AssessmentItem).filter(
        AssessmentItem.form_id == f.id).all()}
    desc = _std_desc_map(db)
    # How many questions on the test assess each standard — so proficiency % is
    # read WITH the evidence behind it (0% on 1 item is weaker than 40% on 9).
    std_items: dict = {}
    for it in items.values():
        if it.scored:
            std_items[it.standard] = std_items.get(it.standard, 0) + 1

    def std_block(subset):
        agg: dict = {}
        for r in subset:
            for std, v in (r.by_standard or {}).items():
                e = agg.setdefault(std, {"earned": 0.0, "possible": 0.0})
                e["earned"] += v.get("earned", 0.0)
                e["possible"] += v.get("possible", 0.0)
        n = len(subset)
        out = []
        for std, v in agg.items():
            pct = round(100.0 * v["earned"] / v["possible"], 1) if v["possible"] else None
            nq = std_items.get(std, 0)
            # Average questions correct per student on this standard.
            avg_correct = round(v["earned"] / n, 1) if n else None
            out.append({"standard": std, "description": desc.get(std, ""),
                        "percent": pct, "questions": nq,
                        "avg_correct": avg_correct, "students": n,
                        **_color_for(f.grade, pct)})
        return sorted(out, key=lambda x: (x["percent"] if x["percent"] is not None else 999))

    def missed_block(subset, n):
        cnt: dict = {}
        for r in subset:
            for pos in (r.missed_positions or []):
                cnt[pos] = cnt.get(pos, 0) + 1
        out = []
        for pos, c in cnt.items():
            it = items.get(pos)
            out.append({
                "position": pos, "missed": c,
                "miss_pct": round(100.0 * c / n, 1) if n else 0,
                "standard": it.standard if it else "",
                "correct_response": it.correct_response if it else "",
                "stem": (it.stem if it else "")[:240]})
        return sorted(out, key=lambda x: -x["missed"])

    # By class.
    by_class: dict = {}
    for r in rows:
        by_class.setdefault(r.teacher_name or "—", []).append(r)
    classes = []
    for cls, subset in sorted(by_class.items()):
        avg = round(sum(r.percent for r in subset) / len(subset), 1)
        bs = std_block(subset)
        di = _di_target(bs)
        # Count the tier of each student ON THE TARGET STANDARD, so a
        # high-average class that still has Red (Intensive) kids is never
        # dismissed as pure enrichment.
        tcounts = {t["name"]: 0 for t in _DI_ROTATION}
        for r in subset:
            by = (r.by_standard or {}).get(di["standard"])
            p = (100.0 * by["earned"] / by["possible"]
                 if by and by.get("possible") else r.percent)
            tcounts[_di_tier_for(p)["name"]] += 1
        red = tcounts.get("Intensive", 0)
        yellow = tcounts.get("Cusp", 0)
        green = tcounts.get("Strategic", 0)
        # A class needs a reteach packet on its weakest standard whenever ANY
        # student is below proficient (Red or Yellow) — the packet tiers them.
        # Enrichment-only when every kid is Green (proficient).
        needs_di = (red > 0 or yellow > 0)
        note = di["note"] if di["note"] and "already proficient" not in di["note"] else ""
        if not needs_di:
            note = "every student is proficient (Green) on the weakest standard"
        classes.append({
            "teacher": cls, "students": len(subset), "avg_percent": avg,
            **_color_for(f.grade, avg),
            "by_standard": bs,
            "di_target": di["standard"], "di_target_pct": di["percent"],
            "needs_di": needs_di, "di_note": note,
            "red_on_target": red, "yellow_on_target": yellow,
            "green_on_target": green,
            "most_missed": missed_block(subset, len(subset))[:5]})

    grade_avg = round(sum(r.percent for r in rows) / len(rows), 1)
    students_list = sorted(
        [{"student_name": r.student_name, "student_id": r.student_id,
          "teacher": r.teacher_name, "percent": r.percent,
          **_color_for(f.grade, r.percent),
          "missed": r.missed_positions or []} for r in rows],
        key=lambda x: (x["teacher"], -x["percent"]))
    return {
        "students": len(rows), "grade_avg": grade_avg,
        **_color_for(f.grade, grade_avg),
        "classes": classes,
        "by_standard": std_block(rows),
        "most_missed": missed_block(rows, len(rows))[:10],
        "students_list": students_list,
    }


def _assessment_results_brief(db, f: AssessmentForm) -> dict | None:
    """A compact results snapshot for the AI Coach: grade avg, per-class avgs,
    the weakest standard, and the most-missed questions. None if no results."""
    n = db.query(TopicResult).filter(TopicResult.form_id == f.id).count()
    if not n:
        return None
    a = _results_analysis(db, f)
    weakest = a["by_standard"][0] if a.get("by_standard") else None
    return {
        "students": a["students"], "grade_avg": a.get("grade_avg"),
        "color": a.get("color"),
        "classes": [{"teacher": c["teacher"], "avg": c["avg_percent"],
                     "color": c["color"]} for c in a.get("classes", [])],
        "weakest_standard": weakest and {
            "standard": weakest["standard"], "percent": weakest["percent"],
            "color": weakest["color"]},
        "most_missed": [{"q": m["position"], "standard": m["standard"],
                         "miss_pct": m["miss_pct"]} for m in a.get("most_missed", [])[:5]],
    }


def _home_results_focus(db, tenant_id) -> list[dict]:
    """Per grade, the most recent topic test WITH results — its grade average,
    the weakest standard to target for DI, and the lowest class — so Home shows
    the coach where to put DI energy this week."""
    forms = (db.query(AssessmentForm)
             .filter(AssessmentForm.tenant_id == tenant_id)
             .order_by(AssessmentForm.grade, AssessmentForm.created_at.desc()).all())
    seen, out = set(), []
    for f in forms:
        if f.grade in seen:
            continue
        brief = _assessment_results_brief(db, f)
        if not brief:
            continue
        seen.add(f.grade)
        classes = brief.get("classes", [])
        lowest = min(classes, key=lambda c: c["avg"]) if classes else None
        out.append({
            "grade": f.grade, "topic": f.topic_code, "form_id": f.id,
            "grade_avg": brief.get("grade_avg"), "color": brief.get("color"),
            "weakest_standard": brief.get("weakest_standard"),
            "lowest_class": lowest,
            "most_missed": brief.get("most_missed", [])[:3]})
    order = {"K": 0, "1": 1, "2": 2, "3": 3, "4": 4}
    out.sort(key=lambda x: order.get(x["grade"], 99))
    return out


@router.get("/assessments/{form_id}/results")
def get_results(
    form_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Scored analysis for a topic test — class averages, per-standard mastery,
    most-missed questions, and the per-student list, all color-coded."""
    f = db.get(AssessmentForm, form_id)
    if not f or f.tenant_id != user.tenant_id:
        raise HTTPException(404, "Assessment not found")
    return {"form": _form_summary(db, f), "analysis": _results_analysis(db, f)}


@router.get("/assessments/{form_id}/results-template.xlsx")
def results_template(
    form_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Download a ready-to-fill results template for this test: Student Name,
    Student ID, Teacher, then Q1..Qn. Fill the letter each student chose."""
    import openpyxl as _oxl
    from fastapi.responses import StreamingResponse

    f = db.get(AssessmentForm, form_id)
    if not f or f.tenant_id != user.tenant_id:
        raise HTTPException(404, "Assessment not found")
    positions = [it.position for it in db.query(AssessmentItem).filter(
        AssessmentItem.form_id == f.id).order_by(AssessmentItem.position).all()]
    wb = _oxl.Workbook()
    ws = wb.active
    ws.title = "Results"
    ws.append(["Student Name", "Student ID", "Teacher"]
              + [f"Q{p}" for p in positions])
    ws.append(["Example, Student", "1234567", "Teacher Name"]
              + ["" for _ in positions])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fn = f"{(f.test_name or 'topic-test')}-results-template.xlsx"
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'})


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
