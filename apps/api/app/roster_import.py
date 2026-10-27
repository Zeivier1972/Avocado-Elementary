"""Importer for the M-DCPS whole-school roster + FAST export.

The export has ONE ROW PER STUDENT PER CLASS PERIOD. Every period row shows
"TBA" for the teacher except the row where Period == 'HR', which carries the
real homeroom teacher and their employee number. We therefore keep each student
exactly ONCE, linked to their homeroom (HR) teacher, and ingest everything the
file gives us for future reference:

  - demographics (name, grade, gender, birth date, FLEID, section)
  - program flags: ESOL/ELL (level + status) and ESE (exceptionality code)
  - FAST Math baseline (overall achievement level + scale score) and the
    per-reporting-category (domain) breakdown, stored for later display.

Detection is by header signature so it routes automatically on upload.
"""
from collections import OrderedDict
from datetime import datetime, timezone
import csv
import io

from app.core.security import hash_password
from app.deps import audit
from app.models import (
    ClassRoom,
    Enrollment,
    Student,
    StudentAssessment,
    User,
)

# Header signature unique to this district export.
_MARKERS = {"student id", "teacher name", "period", "class section number"}

# Grade-3 FAST Math reporting categories (domains). Cat5 is unused at grade 3.
FAST_MATH_CATEGORIES = {
    1: "Number Sense & Operations",
    2: "Fractions",
    3: "Algebraic Reasoning",
    4: "Geometric Reasoning / Measurement & Data",
    5: "Reporting Category 5",
}

# FAST overall is a prior-year result here → the incoming baseline. Labelling it
# "Baseline" (not PM1/2/3) means live PM windows uploaded later automatically
# supersede it in the reports, while it still counts when no PM data exists yet.
BASELINE_PERIOD = "Baseline"


def detect_district_roster(headers) -> bool:
    hs = {(h or "").strip().lower() for h in (headers or [])}
    return _MARKERS.issubset(hs)


def _norm_grade(g: str) -> str:
    g = (g or "").strip().upper()
    if g in ("00", "0", "K", "KG", "KINDER", "KINDERGARTEN"):
        return "K"
    if g in ("PK", "PRE-K", "PREK", "VPK"):
        return "PK"
    return g.lstrip("0") or g  # '03' -> '3'


def _title(name: str) -> str:
    """'VANEGAS LUZ' -> 'Vanegas Luz'; keeps hyphens/apostrophes readable."""
    out = []
    for w in (name or "").split():
        out.append("-".join(p.capitalize() for p in w.split("-")))
    return " ".join(out)


def _int(v):
    v = (v or "").strip()
    return int(v) if v.isdigit() else None


def import_district_roster(db, data: bytes, tenant_id, school_id, user,
                           reconcile: bool = False) -> dict:
    """Upsert the district roster.

    reconcile=False (default): grow & refresh only — add new students, update
    returning ones, never remove anyone. Safe for partial / single-grade files.

    reconcile=True: treat this file as the FULL active roster. Any student in
    this tenant+school whose ID is NOT in the file is soft-withdrawn (flagged,
    history/scores preserved) and dropped from teacher rosters, and stale
    homeroom enrollments (from a mid-year teacher change) are cleared. Only use
    when the upload is the whole school, or it will withdraw everyone missing.
    """
    text = data.decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text)))

    def g(r, k):
        return (r.get(k) or "").strip() if r else ""

    # Group all period-rows by student id (dedup).
    groups: "OrderedDict[str, list]" = OrderedDict()
    for r in rows:
        sid = g(r, "Student ID")
        if sid:
            groups.setdefault(sid, []).append(r)

    existing = {
        s.district_student_id: s
        for s in db.query(Student).filter(
            Student.tenant_id == tenant_id,
            Student.district_student_id.in_(list(groups.keys())),
        ).all()
    }

    teacher_cache: dict = {}
    class_cache: dict = {}
    s_new = s_upd = t_new = c_new = e_new = fast_n = 0
    unassigned = 0
    by_grade: dict = {}
    home_class_by_student: dict = {}  # student.id -> current homeroom class.id

    for sid, rs in groups.items():
        base = rs[0]
        grade = _norm_grade(g(base, "Grade"))
        fn, ln = _title(g(base, "First Name")), _title(g(base, "Last Name"))

        # ---- flags / demographics (kept for future reference & differentiation)
        flags: dict = {}
        esol_lvl, esol_status = g(base, "ESOL Level"), g(base, "ESOL Status")
        if esol_lvl or esol_status:
            flags["ell"] = esol_lvl or esol_status
            if esol_status:
                flags["esol_status"] = esol_status
        ese = g(base, "ESE Exceptionality")
        if ese:
            flags["ese"] = True
            flags["ese_code"] = ese
        for k, col in (("gender", "Gender"), ("fleid", "FLEID"),
                       ("birth_date", "Birth Date"), ("section", "Class Section Number")):
            v = g(base, col)
            if v:
                flags[k] = v

        # ---- FAST Math baseline (overall + domains) if present
        al = g(base, "Fast Math Achievement Level")
        ss = g(base, "Fast Math Scale Score")
        if _int(al) or _int(ss):
            domains = {}
            for i in range(1, 6):
                lvl_col = "Fast Math Cat3 Ach Level 1" if i == 3 else f"Fast Math Cat{i} Ach Level"
                cscale, clvl = g(base, f"Fast Math Cat{i} Scale Score"), g(base, lvl_col)
                if cscale or clvl:
                    domains[FAST_MATH_CATEGORIES[i]] = {
                        "scale": _int(cscale), "level": _int(clvl)}
            flags["fast_math_baseline"] = {
                "level": _int(al),
                "scale": _int(ss),
                "percentile": _int(g(base, "Fast Math Percentile Rank")),
                "school_year": g(base, "FAST Math School Year"),
                "test_month": g(base, "FAST Math Test Month"),
                "domains": domains,
            }

        # ---- upsert the student (once)
        stu = existing.get(sid)
        if stu:
            if fn:
                stu.first_name = fn
            if ln:
                stu.last_name = ln
            if grade:
                stu.grade_level = grade
            merged = {**(stu.flags or {}), **flags}
            merged.pop("withdrawn_at", None)  # legacy JSON marker, if any
            stu.flags = merged
            stu.status = "active"  # present in the file => active again
            s_upd += 1
        else:
            stu = Student(
                tenant_id=tenant_id, school_id=school_id, district_student_id=sid,
                first_name=fn, last_name=ln, grade_level=grade, flags=flags)
            db.add(stu)
            db.flush()
            existing[sid] = stu
            s_new += 1
        by_grade[grade] = by_grade.get(grade, 0) + 1

        # ---- homeroom teacher from the HR row only (skip TBA / blank)
        hr = next((r for r in rs if g(r, "Period").upper() == "HR"), None)
        tname_raw = g(hr, "Teacher Name")
        emp = g(hr, "Employee Number")
        if tname_raw and tname_raw.upper() != "TBA":
            tname = _title(tname_raw)
            key = emp or tname.lower()
            teacher = teacher_cache.get(key)
            if not teacher:
                email = (f"emp{emp}@avocado.edu" if emp
                         else tname.lower().replace(" ", ".") + "@avocado.edu")
                teacher = db.query(User).filter(User.email == email).first()
                if not teacher:
                    teacher = User(
                        tenant_id=tenant_id, school_id=school_id, name=tname,
                        email=email, password_hash=hash_password("demo1234"),
                        role="teacher",
                        scope={"employee_number": emp} if emp else {})
                    db.add(teacher)
                    db.flush()
                    t_new += 1
                teacher_cache[key] = teacher
            cname = f"{grade} - {tname}" if grade else tname
            ckey = (teacher.id, cname)
            cls = class_cache.get(ckey)
            if not cls:
                cls = db.query(ClassRoom).filter(
                    ClassRoom.tenant_id == tenant_id,
                    ClassRoom.teacher_id == teacher.id,
                    ClassRoom.name == cname).first()
                if not cls:
                    cls = ClassRoom(
                        tenant_id=tenant_id, school_id=school_id,
                        teacher_id=teacher.id, name=cname, subject="HOMEROOM",
                        grade_level=grade)
                    db.add(cls)
                    db.flush()
                    c_new += 1
                class_cache[ckey] = cls
            if not db.query(Enrollment).filter(
                    Enrollment.class_id == cls.id,
                    Enrollment.student_id == stu.id).first():
                db.add(Enrollment(class_id=cls.id, student_id=stu.id))
                e_new += 1
            home_class_by_student[stu.id] = cls.id
        else:
            unassigned += 1

        # ---- FAST Math overall as a Baseline assessment (feeds goal / L25 /
        # teacher proficiency until real PM windows are uploaded).
        if _int(al) or _int(ss):
            sa = db.query(StudentAssessment).filter(
                StudentAssessment.tenant_id == tenant_id,
                StudentAssessment.student_id == stu.id,
                StudentAssessment.source == "FAST",
                StudentAssessment.subject == "MATH",
                StudentAssessment.period == BASELINE_PERIOD).first()
            if not sa:
                sa = StudentAssessment(
                    tenant_id=tenant_id, student_id=stu.id, source="FAST",
                    subject="MATH", period=BASELINE_PERIOD)
                db.add(sa)
                fast_n += 1
            sa.level = _int(al)
            sa.scale_score = _int(ss)

    withdrawn = enrollments_cleared = stale_home_cleared = 0
    if reconcile:
        now_iso = datetime.now(timezone.utc).isoformat()
        seen_ids = set(groups.keys())

        # Homeroom class ids for THIS school (so we only clear/count homeroom
        # enrollments, never a student's ELA/MATH class enrollments).
        home_class_ids = {
            c.id for c in db.query(ClassRoom.id).filter(
                ClassRoom.tenant_id == tenant_id,
                ClassRoom.school_id == school_id,
                ClassRoom.subject == "HOMEROOM").all()
        }

        # 1) Soft-withdraw anyone in this school NOT in the uploaded file.
        for stu in db.query(Student).filter(
                Student.tenant_id == tenant_id,
                Student.school_id == school_id).all():
            if stu.district_student_id in seen_ids:
                continue
            if stu.status == "withdrawn":
                continue  # already withdrawn — leave as-is
            stu.status = "withdrawn"
            stu.flags = {**(stu.flags or {}), "withdrawn_at": now_iso}
            # Drop them off teacher homeroom rosters (history/scores untouched).
            enr = db.query(Enrollment).filter(
                Enrollment.student_id == stu.id,
                Enrollment.class_id.in_(home_class_ids)).all() if home_class_ids else []
            for e in enr:
                db.delete(e)
                enrollments_cleared += 1
            withdrawn += 1

        # 2) Clear stale homeroom enrollments for students who changed teachers:
        #    any homeroom enrollment that isn't their current homeroom class.
        for stu_id, cur_cls in home_class_by_student.items():
            for e in db.query(Enrollment).filter(
                    Enrollment.student_id == stu_id,
                    Enrollment.class_id.in_(home_class_ids),
                    Enrollment.class_id != cur_cls).all() if home_class_ids else []:
                db.delete(e)
                stale_home_cleared += 1

    db.commit()
    audit(db, actor=user, action="import", entity_type="roster",
          purpose="district_population_import")

    return {
        "format": "M-DCPS district roster (HR dedup)"
                  + (" — reconciled" if reconcile else ""),
        "reconcile": reconcile,
        "students_created": s_new,
        "students_updated": s_upd,
        "unique_students": len(groups),
        "teachers_created": t_new,
        "classes_created": c_new,
        "enrollments_created": e_new,
        "students_unassigned": unassigned,
        "fast_math_baselines": fast_n,
        "students_withdrawn": withdrawn,
        "withdrawn_enrollments_cleared": enrollments_cleared,
        "stale_homeroom_enrollments_cleared": stale_home_cleared,
        "by_grade": dict(sorted(by_grade.items())),
    }
