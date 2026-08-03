"""Coach section — collaborative planning: pacing calendar + PLC agendas."""
from fastapi import (
    APIRouter,
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
)
from app.export_docx import guide_to_docx
from app.db.session import get_db
from app.deps import audit, get_current_user
from app.models import (
    ClassRoom,
    District,
    PacingTopic,
    PlanningDocument,
    PlcAgenda,
    School,
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


@router.get("/ai-check")
def ai_check(user: User = Depends(_require_coach)):
    """Diagnose the AI configuration (used to troubleshoot guide generation)."""
    return ai_diagnostics()


class AssistantIn(BaseModel):
    message: str
    history: list[dict] = []


def _school_context(db: Session, tenant_id: str) -> dict:
    school = db.query(School).filter(School.tenant_id == tenant_id).first()
    students = db.query(Student).filter(Student.tenant_id == tenant_id).all()
    by_grade: dict[str, int] = {}
    fast_levels: dict[str, int] = {}
    for s in students:
        by_grade[s.grade_level] = by_grade.get(s.grade_level, 0) + 1
        lvl = (s.flags or {}).get("fast_math_level")
        if lvl:
            fast_levels[str(lvl)] = fast_levels.get(str(lvl), 0) + 1
    teachers = (db.query(User)
                .filter(User.tenant_id == tenant_id, User.role == "teacher").all())
    topics = db.query(PacingTopic).filter(
        PacingTopic.tenant_id == tenant_id).all()
    # FAST Math proficiency by grade (level 3+) for the assistant to reason on.
    fast_by_grade: dict[str, dict] = {}
    grade_of = {s.id: s.grade_level for s in students}
    from app.models import StudentAssessment
    for a in db.query(StudentAssessment).filter(
            StudentAssessment.source == "FAST",
            StudentAssessment.subject == "MATH",
            StudentAssessment.tenant_id == tenant_id).all():
        if a.level is None or not (1 <= a.level <= 5):
            continue
        g = grade_of.get(a.student_id, "?")
        d = fast_by_grade.setdefault(g, {}).setdefault(a.period, {"n": 0, "prof": 0})
        d["n"] += 1
        if a.level >= 3:
            d["prof"] += 1
    fast_summary = {
        g: {p: f"{round(100*v['prof']/v['n'])}% (n={v['n']})"
            for p, v in sorted(pd.items())}
        for g, pd in sorted(fast_by_grade.items()) if g in ("K", "1", "2", "3")
    }
    return {
        "school": school.name if school else "",
        "students": len(students),
        "teachers": len(teachers),
        "classes": db.query(ClassRoom).filter(
            ClassRoom.tenant_id == tenant_id).count(),
        "by_grade": dict(sorted(by_grade.items())),
        "fast_levels": dict(sorted(fast_levels.items())),
        "teachers_sample": [t.name for t in teachers[:15]],
        "pacing_topics": [f"G{t.grade_level} {t.topic_code} {t.name}" for t in topics],
        "standards_count": db.query(Standard).count(),
        "fast_math_proficiency_by_grade": fast_summary,
    }


@router.post("/assistant")
def assistant(
    body: AssistantIn,
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """The in-system Expert AI Coach — grounded in live school aggregates."""
    ctx = _school_context(db, user.tenant_id)
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
