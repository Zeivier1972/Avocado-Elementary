"""Seed synthetic, de-identified demo data.

IMPORTANT (docs/00): this is fabricated data — no real students. It lets us
build and demo the full product without any district data-sharing agreement.

Run:  python -m app.seed
"""
import random

from app.core.security import hash_password
from app.db.session import Base, SessionLocal, engine
from app.models import (
    AssessmentDefinition,
    AssessmentResult,
    ClassRoom,
    District,
    Enrollment,
    School,
    Standard,
    StandardMastery,
    Student,
    User,
)

# A small slice of Florida B.E.S.T. standards (grade 3), enough to demo.
STANDARDS = [
    ("ELA", "3", "ELA.3.R.2.2", "Explain how relevant details support the central idea, implied or explicit."),
    ("ELA", "3", "ELA.3.R.1.1", "Explain how characters respond to events/challenges."),
    ("ELA", "3", "ELA.3.C.1.4", "Write expository texts with an organizational structure."),
    ("ELA", "3", "ELA.3.V.1.3", "Use context clues to determine word meaning."),
    ("MATH", "3", "MA.3.NSO.2.1", "Add and subtract multi-digit whole numbers."),
    ("MATH", "3", "MA.3.AR.1.1", "Apply properties of multiplication to solve problems."),
    ("MATH", "3", "MA.3.FR.1.1", "Represent and interpret fractions."),
    ("MATH", "3", "MA.3.GR.1.1", "Describe and classify two-dimensional figures."),
]

FIRST = ["Ana", "Luis", "Sofia", "Ben", "Mia", "Diego", "Chloe", "Noah",
         "Isabella", "Liam", "Emma", "Mateo", "Ava", "Lucas", "Zoe", "Elena",
         "Marcus", "Nina", "Omar", "Priya", "Ruby", "Sam", "Tariq", "Uma"]
LAST = ["R.", "M.", "G.", "P.", "S.", "T.", "V.", "H.", "L.", "C.", "B.", "D."]


def run():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    if db.query(District).first():
        print("Data already present — skipping seed.")
        db.close()
        return

    random.seed(7)
    district = District(name="Miami-Dade County Public Schools (DEMO)", state="FL")
    db.add(district)
    db.flush()
    school = School(tenant_id=district.id, name="Avocado Elementary (DEMO)")
    db.add(school)
    db.flush()

    principal = User(
        tenant_id=district.id, school_id=school.id, name="Paula Principal",
        email="principal@avocado.edu", password_hash=hash_password("demo1234"),
        role="principal", scope={},
    )
    teacher = User(
        tenant_id=district.id, school_id=school.id, name="Tomas Teacher",
        email="teacher@avocado.edu", password_hash=hash_password("demo1234"),
        role="teacher", scope={"subjects": ["ELA"]},
    )
    db.add_all([principal, teacher])
    db.flush()

    std_objs = {}
    for subject, grade, code, desc in STANDARDS:
        s = Standard(
            subject=subject, grade_level=grade, code=code, description=desc,
            details={"learning_targets": [f"I can demonstrate {code}."],
                     "misconceptions": ["Common error placeholder."],
                     "vocabulary": ["term1", "term2"]},
        )
        db.add(s)
        db.flush()
        std_objs[code] = s

    ela_class = ClassRoom(
        tenant_id=district.id, school_id=school.id, teacher_id=teacher.id,
        name="Grade 3 ELA — Rm 210", subject="ELA", grade_level="3",
    )
    db.add(ela_class)
    db.flush()

    ela_standards = [s for c, s in std_objs.items() if s.subject == "ELA"]
    assessment = AssessmentDefinition(
        tenant_id=district.id, school_id=school.id, name="Grade 3 ELA Exit Ticket (DEMO)",
        source="EXIT_TICKET", subject="ELA", grade_level="3",
    )
    db.add(assessment)
    db.flush()

    for i in range(22):
        stu = Student(
            tenant_id=district.id, school_id=school.id,
            district_student_id=f"D3{i:04d}",
            first_name=random.choice(FIRST), last_name=random.choice(LAST),
            grade_level="3",
            flags=_flags(i),
        )
        db.add(stu)
        db.flush()
        db.add(Enrollment(class_id=ela_class.id, student_id=stu.id))
        for std in ela_standards:
            pct = round(random.uniform(0.25, 0.98), 2)
            db.add(AssessmentResult(
                tenant_id=district.id, assessment_id=assessment.id,
                student_id=stu.id, standard_id=std.id, percent_correct=pct,
            ))
            status = ("mastered" if pct >= std.mastery_threshold
                      else "deficient" if pct < 0.5 else "in_progress")
            db.add(StandardMastery(
                tenant_id=district.id, student_id=stu.id, standard_id=std.id,
                mastery_pct=pct, status=status,
                trend=random.choice(["up", "flat", "down"]),
            ))

    db.commit()
    db.close()
    print("Seeded demo data.")
    print("  Principal: principal@avocado.edu / demo1234")
    print("  Teacher:   teacher@avocado.edu   / demo1234")


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
