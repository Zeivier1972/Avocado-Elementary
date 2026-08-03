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
    SavedGuide,
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


def _save_guide(db, user, grade_level, topic_code, subject, guide) -> str:
    """Persist a generated guide so it survives navigating away."""
    rec = SavedGuide(
        tenant_id=user.tenant_id, grade_level=grade_level or "",
        topic_code=topic_code or "", subject=(subject or "MATH"),
        title=guide.get("title", "Planning Guide"), content=guide,
        ai_generated=bool(guide.get("ai_generated")), created_by=user.id)
    db.add(rec)
    db.commit()
    return rec.id


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
    guide_id = _save_guide(db, user, t.grade_level, t.topic_code, t.subject, guide)
    audit(db, actor=user, action="generate", entity_type="planning_guide",
          entity_id=guide_id, purpose="collaborative_planning")
    return {"topic": t.name, "guide": guide, "guide_id": guide_id}


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
    file: UploadFile = File(...),
    grade_level: str = Form(...),
    subject: str = Form("MATH"),
    topic_name: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """One step: upload a topic's pacing guide -> create the topic (folder),
    store the file in it, and generate the Collaborative Planning Guide from the
    document's content. This is the primary 'upload a new topic' flow."""
    import re as _re
    from app.ai import generate_guide_from_pacing
    from app.doc_text import extract_document_text

    data = await file.read()
    if len(data) > _MAX_DOC_BYTES:
        raise HTTPException(400, "File is larger than the 25 MB limit.")
    text, reason = extract_document_text(file.filename, file.content_type, data)
    if not text:
        raise HTTPException(
            400, f"Could not read this document's text: {reason}. "
                 "Upload a text-based PDF, Word, or Excel pacing guide.")

    # Name / code: "Topic 1: Understand Multiplication" -> code "Topic 1",
    # name "Understand Multiplication". Otherwise use the filename.
    label = (topic_name or "").strip() or file.filename.rsplit(".", 1)[0]
    if ":" in label:
        code, name = [x.strip() for x in label.split(":", 1)]
    else:
        m = _re.search(r"(topic\s*\w+|chapter\s*\w+)", label, _re.I)
        code = m.group(1).title() if m else label[:40]
        name = label
    benchmarks = list(dict.fromkeys(_re.findall(r"MA\.\w+\.\w+\.\d+\.\d+", text)))

    last = (db.query(PacingTopic)
            .filter(PacingTopic.tenant_id == user.tenant_id,
                    PacingTopic.grade_level == grade_level)
            .order_by(PacingTopic.week_order.desc()).first())
    topic = PacingTopic(
        tenant_id=user.tenant_id, subject=(subject or "MATH").upper(),
        grade_level=grade_level, topic_code=code, name=name,
        benchmarks=benchmarks, learning_target="", quarter="",
        week_order=((last.week_order + 1) if last else 0),
        source="Uploaded pacing guide", lessons=[])
    db.add(topic)
    db.flush()

    doc = PlanningDocument(
        tenant_id=user.tenant_id, grade_level=grade_level, topic_code=code,
        subject=(subject or "MATH").upper(), name=file.filename,
        filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        size=len(data), data=data, uploaded_by=user.id)
    db.add(doc)
    db.commit()

    standards = _resolve_standards(db, benchmarks) if benchmarks else []
    guide = generate_guide_from_pacing(
        text, standards, grade_level, (subject or "MATH").upper(), name)
    guide_id = _save_guide(db, user, grade_level, code, subject, guide)
    audit(db, actor=user, action="generate", entity_type="planning_guide",
          entity_id=guide_id, purpose="upload_pacing_and_generate")
    return {
        "topic": {"id": topic.id, "topic_code": code, "name": name},
        "guide": guide, "document_id": doc.id, "guide_id": guide_id,
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
    db: Session = Depends(get_db),
    user: User = Depends(_require_coach),
):
    """Read an uploaded pacing-guide document and generate the Collaborative
    Planning Guide from its content (grounded in the referenced B1G-M benchmarks
    + ALDs)."""
    import re as _re
    from app.ai import generate_guide_from_pacing
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
    if d.topic_code:
        topic = db.query(PacingTopic).filter(
            PacingTopic.tenant_id == user.tenant_id,
            PacingTopic.topic_code == d.topic_code,
            PacingTopic.grade_level == d.grade_level).first()
        if topic and topic.benchmarks:
            for c in topic.benchmarks:
                if c not in codes:
                    codes.append(c)
    standards = _resolve_standards(db, codes) if codes else []
    topic_name = d.topic_code or d.name.rsplit(".", 1)[0]

    guide = generate_guide_from_pacing(
        text, standards, d.grade_level, d.subject or "MATH", topic_name)
    guide_id = _save_guide(db, user, d.grade_level, d.topic_code, d.subject, guide)
    audit(db, actor=user, action="generate", entity_type="planning_guide",
          entity_id=guide_id, purpose="guide_from_pacing_document")
    return {"topic": topic_name, "guide": guide, "guide_id": guide_id,
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
    return {"id": g.id, "title": g.title, "guide": g.content}


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
