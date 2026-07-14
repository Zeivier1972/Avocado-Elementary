"""School population (roster) import and summary — the foundation for tracking
teacher and student performance toward the school goal."""
import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import get_db
from app.deps import audit, get_current_user
from app.models import ClassRoom, District, Enrollment, School, Student, User

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
