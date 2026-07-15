"""School population (roster) import and summary — the foundation for tracking
teacher and student performance toward the school goal."""
import csv
import io
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import get_db
from app.deps import audit, get_current_user
from app.fast_import import detect as detect_fast
from app.fast_import import parse_fast_export
from app.import_excel import parse_workbook
from app.models import (
    ClassRoom,
    District,
    Enrollment,
    School,
    Student,
    StudentAssessment,
    StudentBenchmarkResult,
    User,
)

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_ROLES = {"principal", "ap", "district_admin", "instructional_coach",
               "math_coach", "reading_coach", "support_staff"}

# Flexible header matching: canonical field -> accepted header spellings.
FIELD_ALIASES = {
    "student_id": ["student_district_id", "district_student_id", "student_id",
                   "studentid", "student number", "student id", "local id",
                   "id", "id number"],
    "first_name": ["first_name", "firstname", "first", "student first name"],
    "last_name": ["last_name", "lastname", "last", "student last name"],
    "grade": ["grade", "grade_level", "gradelevel", "grd", "grade level"],
    "teacher_email": ["teacher_email", "teacheremail", "teacher e-mail"],
    "teacher_name": ["teacher", "teacher_name", "teachername", "teacher name",
                     "homeroom teacher", "teacher last name"],
    "class_name": ["class", "homeroom", "classroom", "section", "room",
                   "class name", "class section number"],
    "course": ["course title", "course", "course name"],
    "subject": ["subject", "content"],
    "ell": ["ell", "esol", "lep", "ell level", "esol level"],
    "ese": ["ese", "exceptionality", "swd", "sped", "ese exceptionality"],
    "plan504": ["504", "plan_504", "504 plan"],
    "mtss": ["mtss", "tier", "mtss_tier", "mtss tier"],
    "fast_math_scale": ["fast math scale score", "math scale score",
                        "fast math scale"],
    "fast_math_level": ["fast math achievement level", "math achievement level",
                        "fast math level"],
}


COURSE_SUBJECT = [
    ("math", "MATH"), ("reading", "ELA"), ("language arts", "ELA"),
    ("writing", "ELA"), ("ela", "ELA"), ("science", "SCIENCE"),
    ("social", "SOCIAL_STUDIES"), ("homeroom", "HOMEROOM"),
]


def _teacher_from_section(section: str) -> str:
    """Derive a teacher name from a sheet/section label.
    'K01 - Mathis' -> 'Mathis'; 'T11 VPK - Guerrero' -> 'Guerrero';
    'Porco  St. Aubin' -> 'Porco St. Aubin' (tracker sheets are teacher names)."""
    s = (section or "").strip()
    if not s:
        return ""
    if " - " in s:
        s = s.split(" - ", 1)[1]
    return re.sub(r"\s+", " ", s).strip()


def _subject_from_course(course: str, fallback: str) -> str:
    c = (course or "").lower()
    for key, subj in COURSE_SUBJECT:
        if key in c:
            return subj
    return fallback


def _norm(s: str) -> str:
    return (s or "").strip().lower().replace("_", " ")


def _build_map(headers: list[str]) -> dict:
    norm = {_norm(h): h for h in headers}
    field_map = {}
    for field, aliases in FIELD_ALIASES.items():
        for a in aliases:
            if _norm(a) in norm:
                field_map[field] = norm[_norm(a)]
                break
    return field_map


def _require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Leadership/coach role required")
    return user


@router.post("/roster/import")
async def import_roster(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
):
    raw = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    fmap = _build_map(reader.fieldnames or [])
    missing = [f for f in ("student_id", "first_name", "last_name", "grade")
               if f not in fmap]
    if missing:
        raise HTTPException(
            400,
            f"CSV is missing required column(s): {', '.join(missing)}. "
            f"Detected headers: {reader.fieldnames}",
        )

    district = db.query(District).first()
    school = db.query(School).filter(School.tenant_id == district.id).first()
    tenant_id, school_id = district.id, school.id

    students_new = students_upd = teachers_new = classes_new = enroll_new = 0
    errors: list[str] = []
    teacher_cache: dict[str, User] = {}
    class_cache: dict[tuple, ClassRoom] = {}
    student_cache: dict[str, Student] = {}

    def get(row, field):
        col = fmap.get(field)
        return (row.get(col, "") or "").strip() if col else ""

    for i, row in enumerate(reader, start=2):
        sid = get(row, "student_id")
        fn, ln = get(row, "first_name"), get(row, "last_name")
        grade = get(row, "grade").upper().replace("GRADE", "").strip() or ""
        if grade in ("K", "KG", "KINDER", "KINDERGARTEN", "0", "00"):
            grade = "K"
        elif grade in ("PK", "PRE-K", "PREK"):
            grade = "PK"
        if not sid or not fn:
            errors.append(f"row {i}: missing student id or name")
            continue

        flags = {}
        ell = get(row, "ell")
        if ell and ell not in ("0", "z", "zz"):
            flags["ell"] = ell
        ese = get(row, "ese")
        if ese and ese.lower() not in ("n", "no", "none", "0"):
            flags["ese"] = True
            flags["ese_code"] = ese
        if get(row, "plan504").lower() in ("y", "yes", "true", "1"):
            flags["504"] = True
        if get(row, "mtss"):
            flags["mtss_tier"] = get(row, "mtss")
        fast_scale = get(row, "fast_math_scale")
        fast_level = get(row, "fast_math_level")
        if fast_scale and fast_scale.isdigit():
            flags["fast_math_scale"] = int(fast_scale)
        if fast_level:
            flags["fast_math_level"] = fast_level

        student = student_cache.get(sid) or (
            db.query(Student)
            .filter(Student.tenant_id == tenant_id,
                    Student.district_student_id == sid)
            .first()
        )
        if student:
            student.first_name, student.last_name = fn, ln
            student.grade_level = grade
            # merge flags across the student's multiple course rows
            student.flags = {**(student.flags or {}), **flags}
            if sid not in student_cache:
                students_upd += 1
        else:
            student = Student(
                tenant_id=tenant_id, school_id=school_id,
                district_student_id=sid, first_name=fn, last_name=ln,
                grade_level=grade, flags=flags)
            db.add(student)
            db.flush()
            students_new += 1
        student_cache[sid] = student

        # Teacher (optional) -> upsert a User(role=teacher).
        temail = get(row, "teacher_email").lower()
        tname = get(row, "teacher_name")
        teacher = None
        key = temail or tname.lower()
        if key:
            if key in teacher_cache:
                teacher = teacher_cache[key]
            else:
                if not temail:
                    temail = (tname.lower().replace(" ", ".") + "@avocado.edu")
                teacher = db.query(User).filter(User.email == temail).first()
                if not teacher:
                    teacher = User(
                        tenant_id=tenant_id, school_id=school_id,
                        name=tname or temail, email=temail,
                        password_hash=hash_password("demo1234"),
                        role="teacher", scope={})
                    db.add(teacher)
                    db.flush()
                    teachers_new += 1
                teacher_cache[key] = teacher

        # Class + enrollment (only if we have a teacher).
        if teacher:
            course = get(row, "course")
            subject = _subject_from_course(
                course, (get(row, "subject") or "HOMEROOM").upper())
            cname = course or get(row, "class_name") or f"Grade {grade} {subject.title()}"
            ckey = (teacher.id, cname, subject, grade)
            cls = class_cache.get(ckey)
            if not cls:
                cls = (db.query(ClassRoom)
                       .filter(ClassRoom.teacher_id == teacher.id,
                               ClassRoom.name == cname).first())
                if not cls:
                    cls = ClassRoom(
                        tenant_id=tenant_id, school_id=school_id,
                        teacher_id=teacher.id, name=cname, subject=subject,
                        grade_level=grade)
                    db.add(cls)
                    db.flush()
                    classes_new += 1
                class_cache[ckey] = cls
            exists = (db.query(Enrollment)
                      .filter(Enrollment.class_id == cls.id,
                              Enrollment.student_id == student.id).first())
            if not exists:
                db.add(Enrollment(class_id=cls.id, student_id=student.id))
                enroll_new += 1

    db.commit()
    audit(db, actor=user, action="import", entity_type="roster",
          purpose="school_population_import")
    return {
        "students_created": students_new, "students_updated": students_upd,
        "teachers_created": teachers_new, "classes_created": classes_new,
        "enrollments_created": enroll_new,
        "errors": errors[:50], "error_count": len(errors),
        "column_mapping": fmap,
    }


@router.post("/import/excel")
async def import_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
):
    """Import a district Excel workbook (Class Lists or Topic Assessment Tracker).
    Upserts students and their longitudinal assessments (FAST / iReady / Topic).
    Import Class Lists first so grades are established, then the Tracker."""
    data = await file.read()
    district = db.query(District).first()
    school = db.query(School).filter(School.tenant_id == district.id).first()
    tenant_id, school_id = district.id, school.id

    # FLDOE FAST item-level export gets its own richer path (benchmark results).
    if detect_fast(data):
        return _import_fast_export(db, data, tenant_id, school_id, user)

    try:
        records = parse_workbook(data)
    except Exception as e:
        raise HTTPException(400, f"Could not parse workbook: {e}")
    if not records:
        raise HTTPException(400, "No student rows found. Check the file format.")

    # Merge parsed rows by student id (a student may appear on multiple sheets).
    merged: dict[str, dict] = {}
    for rec in records:
        sid = rec["student"]["id"]
        m = merged.setdefault(sid, {"student": rec["student"], "assessments": []})
        # keep a non-empty grade if a later row provides one
        if not m["student"].get("grade") and rec["student"].get("grade"):
            m["student"]["grade"] = rec["student"]["grade"]
        m["student"]["flags"] = {**m["student"].get("flags", {}),
                                 **rec["student"].get("flags", {})}
        m["assessments"].extend(rec["assessments"])
        m.setdefault("sections", set()).add(rec.get("section", ""))

    # Preload existing students + their assessments for the touched ids.
    ids = list(merged.keys())
    existing_students = {
        s.district_student_id: s
        for s in db.query(Student).filter(
            Student.tenant_id == tenant_id,
            Student.district_student_id.in_(ids)).all()
    }
    students_new = students_upd = asmt_new = asmt_upd = 0
    by_grade: dict[str, int] = {}
    by_type: dict[str, int] = {}
    teacher_cache: dict[str, User] = {}
    class_cache: dict[str, ClassRoom] = {}

    for sid, m in merged.items():
        sd = m["student"]
        stu = existing_students.get(sid)
        if stu:
            if sd.get("first_name"):
                stu.first_name = sd["first_name"]
            if sd.get("last_name"):
                stu.last_name = sd["last_name"]
            if sd.get("grade"):
                stu.grade_level = sd["grade"]
            stu.flags = {**(stu.flags or {}), **sd.get("flags", {})}
            students_upd += 1
        else:
            stu = Student(
                tenant_id=tenant_id, school_id=school_id, district_student_id=sid,
                first_name=sd.get("first_name", ""), last_name=sd.get("last_name", ""),
                grade_level=sd.get("grade", ""), flags=sd.get("flags", {}))
            db.add(stu)
            db.flush()
            existing_students[sid] = stu
            students_new += 1
        by_grade[stu.grade_level] = by_grade.get(stu.grade_level, 0) + 1

        # Link the student to their teacher's class (from the sheet name), so
        # per-teacher reports work. e.g. "301 - Porco" -> teacher Porco.
        for section in m.get("sections", set()):
            tname = _teacher_from_section(section)
            if not tname:
                continue
            teacher = teacher_cache.get(tname.lower())
            if not teacher:
                temail = tname.lower().replace(" ", ".") + "@avocado.edu"
                teacher = db.query(User).filter(User.email == temail).first()
                if not teacher:
                    teacher = User(
                        tenant_id=tenant_id, school_id=school_id, name=tname,
                        email=temail, password_hash=hash_password("demo1234"),
                        role="teacher", scope={})
                    db.add(teacher)
                    db.flush()
                teacher_cache[tname.lower()] = teacher
            cname = section or f"Grade {stu.grade_level} - {tname}"
            cls = class_cache.get(cname)
            if not cls:
                cls = db.query(ClassRoom).filter(
                    ClassRoom.tenant_id == tenant_id,
                    ClassRoom.name == cname).first()
                if not cls:
                    cls = ClassRoom(
                        tenant_id=tenant_id, school_id=school_id,
                        teacher_id=teacher.id, name=cname, subject="HOMEROOM",
                        grade_level=stu.grade_level)
                    db.add(cls)
                    db.flush()
                class_cache[cname] = cls
            if not db.query(Enrollment).filter(
                    Enrollment.class_id == cls.id,
                    Enrollment.student_id == stu.id).first():
                db.add(Enrollment(class_id=cls.id, student_id=stu.id))

        # Existing assessments for this student, keyed for idempotent upsert.
        prior = {
            (a.source, a.subject, a.period): a
            for a in db.query(StudentAssessment).filter(
                StudentAssessment.student_id == stu.id).all()
        }
        seen = set()
        for a in m["assessments"]:
            key = (a["source"], a["subject"], a["period"])
            if key in seen:
                continue
            seen.add(key)
            by_type[f"{a['source']}/{a['subject']}"] = \
                by_type.get(f"{a['source']}/{a['subject']}", 0) + 1
            rec = prior.get(key)
            if rec:
                if a.get("level") is not None:
                    rec.level = a["level"]
                if a.get("scale_score") is not None:
                    rec.scale_score = a["scale_score"]
                if a.get("percent") is not None:
                    rec.percent = a["percent"]
                asmt_upd += 1
            else:
                db.add(StudentAssessment(
                    tenant_id=tenant_id, student_id=stu.id,
                    source=a["source"], subject=a["subject"], period=a["period"],
                    level=a.get("level"), scale_score=a.get("scale_score"),
                    percent=a.get("percent"), label=a.get("label", "")))
                asmt_new += 1

    db.commit()
    audit(db, actor=user, action="import", entity_type="assessments_excel",
          purpose="assessment_import")
    return {
        "students_created": students_new, "students_updated": students_upd,
        "assessments_created": asmt_new, "assessments_updated": asmt_upd,
        "students_by_grade": dict(sorted(by_grade.items())),
        "assessment_counts": dict(sorted(by_type.items())),
    }


def _import_fast_export(db, data, tenant_id, school_id, user):
    """Store a FLDOE FAST item export: FAST scale/level summary + per-benchmark
    item results (for domain/benchmark analysis)."""
    parsed = parse_fast_export(data)
    subject, period = parsed["subject"], parsed["period"]
    ids = [s["district_student_id"] for s in parsed["students"]]
    existing = {
        s.district_student_id: s
        for s in db.query(Student).filter(
            Student.tenant_id == tenant_id,
            Student.district_student_id.in_(ids)).all()
    }
    students_new = items_new = 0
    for sd in parsed["students"]:
        sid = sd["district_student_id"]
        stu = existing.get(sid)
        flags = {}
        if sd.get("ell") and sd["ell"].lower() not in ("no", "n", ""):
            flags["ell"] = sd["ell"]
        if sd.get("ese") and sd["ese"][:1] not in ("N", "n", ""):
            flags["ese"] = True
        if not stu:
            stu = Student(
                tenant_id=tenant_id, school_id=school_id, district_student_id=sid,
                first_name=sd.get("first_name", ""), last_name=sd.get("last_name", ""),
                grade_level=(sd.get("grade") or "").strip(), flags=flags)
            db.add(stu)
            db.flush()
            existing[sid] = stu
            students_new += 1
        else:
            if sd.get("grade"):
                stu.grade_level = sd["grade"].strip()
            stu.flags = {**(stu.flags or {}), **flags}

        # FAST summary assessment (level + scale), idempotent per period.
        summ = (db.query(StudentAssessment).filter(
            StudentAssessment.student_id == stu.id,
            StudentAssessment.source == "FAST",
            StudentAssessment.subject == subject,
            StudentAssessment.period == period).first())
        if not summ:
            summ = StudentAssessment(
                tenant_id=tenant_id, student_id=stu.id, source="FAST",
                subject=subject, period=period)
            db.add(summ)
        summ.level = sd.get("level")
        summ.scale_score = sd.get("scale_score")

        # Replace prior benchmark results for this student/subject/period.
        db.query(StudentBenchmarkResult).filter(
            StudentBenchmarkResult.student_id == stu.id,
            StudentBenchmarkResult.subject == subject,
            StudentBenchmarkResult.period == period).delete()
        for idx, it in enumerate(sd["items"]):
            db.add(StudentBenchmarkResult(
                tenant_id=tenant_id, student_id=stu.id, source="FAST",
                subject=subject, period=period, category=it["category"],
                benchmark_code=it["benchmark_code"],
                points_earned=it["earned"], points_possible=it["possible"],
                item_index=idx))
            items_new += 1

    db.commit()
    audit(db, actor=user, action="import", entity_type="fast_export",
          purpose="assessment_import")
    return {
        "format": "FAST item export", "subject": subject, "period": period,
        "students": len(parsed["students"]), "students_created": students_new,
        "benchmark_results_created": items_new,
    }


@router.get("/school/summary")
def school_summary(
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
):
    district = db.query(District).first()
    if not district:
        return {"students": 0, "teachers": 0, "classes": 0, "by_grade": {}}
    students = db.query(Student).filter(Student.tenant_id == district.id).all()
    by_grade: dict[str, int] = {}
    for s in students:
        by_grade[s.grade_level] = by_grade.get(s.grade_level, 0) + 1
    teachers = (db.query(User)
                .filter(User.tenant_id == district.id, User.role == "teacher")
                .count())
    classes = db.query(ClassRoom).filter(
        ClassRoom.tenant_id == district.id).count()
    return {
        "students": len(students), "teachers": teachers, "classes": classes,
        "by_grade": dict(sorted(by_grade.items())),
    }
