"""Seed demo data + load the REAL Florida B.E.S.T. Math standards and the
M-DCPS pacing guide extracted from the district documents.

IMPORTANT (docs/00): student data here is fabricated/de-identified. The
standards and pacing content come from official M-DCPS / FLDOE documents.

Run:  python -m app.seed
"""
import json
import random
from pathlib import Path

from app.core.security import hash_password
from app.db.session import Base, SessionLocal, engine
from app.models import (
    AssessmentDefinition,
    AssessmentResult,
    ClassRoom,
    District,
    Enrollment,
    PacingTopic,
    School,
    Standard,
    StandardMastery,
    Student,
    User,
)

DATA = Path(__file__).parent / "data"

# ELA demo standards (keep the teacher demo flow working).
ELA_STANDARDS = [
    ("ELA", "3", "ELA.3.R.2.2", "Explain how relevant details support the central idea, implied or explicit."),
    ("ELA", "3", "ELA.3.R.1.1", "Explain how characters respond to events/challenges."),
    ("ELA", "3", "ELA.3.C.1.4", "Write expository texts with an organizational structure."),
    ("ELA", "3", "ELA.3.V.1.3", "Use context clues to determine word meaning."),
]

FIRST = ["Ana", "Luis", "Sofia", "Ben", "Mia", "Diego", "Chloe", "Noah",
         "Isabella", "Liam", "Emma", "Mateo", "Ava", "Lucas", "Zoe", "Elena",
         "Marcus", "Nina", "Omar", "Priya", "Ruby", "Sam", "Tariq", "Uma"]
LAST = ["R.", "M.", "G.", "P.", "S.", "T.", "V.", "H.", "L.", "C.", "B.", "D."]


def _load_math_standards(db, existing_codes):
    path = DATA / "standards_math.json"
    if not path.exists():
        print("  (standards_math.json missing — skipping math standards)")
        return 0
    rows = json.loads(path.read_text())
    n = 0
    for r in rows:
        if r["code"] in existing_codes:
            continue
        db.add(Standard(
            subject="MATH", grade_level=r["grade"], code=r["code"],
            description=r["description"], mastery_threshold=0.7,
            details={
                "clarifications": r.get("clarifications", []),
                "prerequisites": r.get("prerequisites", []),
                "next": r.get("next", []),
                "misconceptions": r.get("misconceptions", ""),
                "strategies": r.get("strategies", ""),
                "strand": r.get("strand", ""),
            },
        ))
        existing_codes.add(r["code"])
        n += 1
    return n


def _load_pacing(db, tenant_id):
    path = DATA / "pacing_g3.json"
    if not path.exists():
        print("  (pacing_g3.json missing — skipping pacing)")
        return 0
    p = json.loads(path.read_text())
    n = 0
    for order, t in enumerate(p.get("topics", [])):
        db.add(PacingTopic(
            tenant_id=tenant_id, subject=p["subject"], grade_level=p["grade"],
            topic_code=t["topic_code"], chapter=t.get("chapter", ""),
            name=t["name"], quarter=t.get("quarter", ""), week_order=order,
            benchmarks=t.get("benchmarks", []),
            learning_target=t.get("learning_target", ""),
            success_criteria=t.get("success_criteria", []),
            vocabulary=t.get("vocabulary", []),
            source=p.get("source", ""),
        ))
        n += 1
    return n


def _get_or_create_user(db, *, tenant_id, school_id, name, email, role, scope):
    u = db.query(User).filter(User.email == email).first()
    if u:
        return u, False
    u = User(tenant_id=tenant_id, school_id=school_id, name=name, email=email,
             password_hash=hash_password("demo1234"), role=role, scope=scope)
    db.add(u)
    db.flush()
    return u, True


def run():
    """Idempotent seed: safe to run on every deploy. Adds any missing users,
    standards, and pacing without duplicating the student demo."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    random.seed(7)

    district = db.query(District).first()
    if not district:
        district = District(name="Miami-Dade County Public Schools (DEMO)", state="FL")
        db.add(district)
        db.flush()
    school = db.query(School).filter(School.tenant_id == district.id).first()
    if not school:
        school = School(tenant_id=district.id, name="Avocado Elementary (DEMO)")
        db.add(school)
        db.flush()

    principal, _ = _get_or_create_user(
        db, tenant_id=district.id, school_id=school.id, name="Paula Principal",
        email="principal@avocado.edu", role="principal", scope={})
    teacher, _ = _get_or_create_user(
        db, tenant_id=district.id, school_id=school.id, name="Tomas Teacher",
        email="teacher@avocado.edu", role="teacher", scope={"subjects": ["ELA"]})
    coach, coach_new = _get_or_create_user(
        db, tenant_id=district.id, school_id=school.id, name="Maria Math Coach",
        email="coach@avocado.edu", role="math_coach", scope={"subjects": ["MATH"]})

    # Standards: ELA demo set + REAL math library (idempotent by code).
    codes = {c for (c,) in db.query(Standard.code).all()}
    std_objs = {}
    for subject, grade, code, desc in ELA_STANDARDS:
        if code in codes:
            std_objs[code] = db.query(Standard).filter(Standard.code == code).first()
            continue
        s = Standard(subject=subject, grade_level=grade, code=code, description=desc,
                     details={"learning_targets": [f"I can demonstrate {code}."],
                              "misconceptions": ["Common error placeholder."],
                              "vocabulary": ["term1", "term2"]})
        db.add(s)
        db.flush()
        std_objs[code] = s
        codes.add(code)
    n_math = _load_math_standards(db, codes)
    n_pacing = 0
    if not db.query(PacingTopic).first():
        n_pacing = _load_pacing(db, district.id)
    db.flush()

    # Student demo (ELA) — only build once, guarded by class existence.
    if db.query(ClassRoom).first():
        db.commit()
        db.close()
        print("Standards/pacing/users synced (student demo already present).")
        print(f"  Math standards now present total; pacing topics added: {n_pacing}")
        print(f"  Coach account {'created' if coach_new else 'already existed'}: "
              "coach@avocado.edu / demo1234")
        return

    ela_class = ClassRoom(
        tenant_id=district.id, school_id=school.id, teacher_id=teacher.id,
        name="Grade 3 ELA — Rm 210", subject="ELA", grade_level="3")
    db.add(ela_class)
    db.flush()

    ela_standards = [s for c, s in std_objs.items() if s and s.subject == "ELA"]
    assessment = AssessmentDefinition(
        tenant_id=district.id, school_id=school.id,
        name="Grade 3 ELA Exit Ticket (DEMO)", source="EXIT_TICKET",
        subject="ELA", grade_level="3")
    db.add(assessment)
    db.flush()

    for i in range(22):
        stu = Student(
            tenant_id=district.id, school_id=school.id,
            district_student_id=f"D3{i:04d}",
            first_name=random.choice(FIRST), last_name=random.choice(LAST),
            grade_level="3", flags=_flags(i))
        db.add(stu)
        db.flush()
        db.add(Enrollment(class_id=ela_class.id, student_id=stu.id))
        for std in ela_standards:
            pct = round(random.uniform(0.25, 0.98), 2)
            db.add(AssessmentResult(
                tenant_id=district.id, assessment_id=assessment.id,
                student_id=stu.id, standard_id=std.id, percent_correct=pct))
            status = ("mastered" if pct >= std.mastery_threshold
                      else "deficient" if pct < 0.5 else "in_progress")
            db.add(StandardMastery(
                tenant_id=district.id, student_id=stu.id, standard_id=std.id,
                mastery_pct=pct, status=status,
                trend=random.choice(["up", "flat", "down"])))

    db.commit()
    db.close()
    print("Seeded demo data.")
    print(f"  Real math standards loaded: {n_math}")
    print(f"  Pacing topics loaded: {n_pacing}")
    print("  Principal: principal@avocado.edu / demo1234")
    print("  Teacher:   teacher@avocado.edu   / demo1234")
    print("  Coach:     coach@avocado.edu     / demo1234")


def _flags(i: int) -> dict:
    f = {}
    if i % 4 == 0:
        f["ell"] = f"L{random.randint(1, 4)}"
    if i % 6 == 0:
        f["ese"] = True
    if i % 5 == 0:
        f["mtss_tier"] = random.choice([2, 3])
    return f


if __name__ == "__main__":
    run()
