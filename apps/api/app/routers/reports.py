"""Grade-level performance analytics — the goal-tracking reports built from
imported FAST / iReady / Topic assessment data."""
import re
from collections import defaultdict

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user
from app.goal_rubric import topic_level
from app.models import (
    ClassRoom,
    Enrollment,
    Standard,
    Student,
    StudentAssessment,
    StudentBenchmarkResult,
    User,
)

router = APIRouter(prefix="/reports", tags=["reports"])

# FAST achievement levels are 1-5; level >= 3 is proficient.
FAST_PERIODS = ["PM1", "PM2", "PM3"]
# "Baseline" = prior-year FAST carried in on the roster; shown until PM windows
# are uploaded, and reported alongside them.
FAST_REPORT_PERIODS = ["Baseline"] + FAST_PERIODS
IREADY_PERIODS = ["AP1", "AP2", "AP3"]


def _is_level(v):
    return v is not None and 1 <= v <= 5


def _fast_summary(rows, subject):
    """Proficiency (%level>=3) by period for a FAST subject."""
    by_period = defaultdict(list)
    for a in rows:
        if a.source == "FAST" and a.subject == subject and _is_level(a.level):
            by_period[a.period].append(int(a.level))
    out = {}
    for p in FAST_REPORT_PERIODS:
        levels = by_period.get(p, [])
        if not levels:
            continue
        dist = {str(i): levels.count(i) for i in range(1, 6)}
        prof = sum(1 for x in levels if x >= 3)
        out[p] = {"n": len(levels), "proficient": prof,
                  "pct_proficient": round(100 * prof / len(levels)),
                  "distribution": dist,
                  "avg_level": round(sum(levels) / len(levels), 2)}
    return out


def _iready_summary(rows, subject):
    by_period = defaultdict(list)
    for a in rows:
        if a.source == "IREADY" and a.subject == subject and a.level is not None:
            by_period[a.period].append(int(a.level))
    out = {}
    for p in IREADY_PERIODS:
        lv = by_period.get(p, [])
        if lv:
            # iReady placement: 3 = below (2 grades+), report % on/above (level 1)
            out[p] = {"n": len(lv),
                      "distribution": {str(i): lv.count(i) for i in sorted(set(lv))}}
    return out


def _topic_summary(rows):
    by_topic = defaultdict(list)
    for a in rows:
        if a.source == "TOPIC" and a.percent is not None:
            by_topic[a.period].append(a.percent)
    return {
        p: {"avg_pct": round(100 * sum(v) / len(v)), "n": len(v)}
        for p, v in sorted(by_topic.items(),
                           key=lambda kv: _topic_order(kv[0]))
    }


def _topic_order(period):
    import re
    m = re.search(r"\d+", period)
    return int(m.group()) if m else 99


def _pct_l3_by_period(rows, source, subject, periods):
    """% Level 3+ by period for (source, subject) over a list of assessments."""
    by = defaultdict(lambda: [0, 0])
    for a in rows:
        if a.source != source or a.subject != subject or a.level is None:
            continue
        if source == "FAST" and not (1 <= a.level <= 5):
            continue
        by[a.period][1] += 1
        if a.level >= 3:
            by[a.period][0] += 1
    return {p: {"pct": round(100 * by[p][0] / by[p][1]), "n": by[p][1]}
            for p in periods if by[p][1]}


def _latest_level(rows, source, subject, periods):
    """Latest available level per student for (source, subject)."""
    best = {}
    for a in rows:
        if a.source != source or a.subject != subject or a.level is None:
            continue
        order = periods.index(a.period) if a.period in periods else -1
        cur = best.get(a.student_id)
        if cur is None or order > cur[0]:
            best[a.student_id] = (order, a.level)
    return {sid: lv for sid, (_, lv) in best.items()}


@router.get("/school-goal")
def school_goal(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """School-wide progress toward the goal: Level 3+ in BOTH FAST Math and
    i-Ready Math, by grade and school-wide, across PM1->PM3 and AP1->AP3."""
    students = db.query(Student).filter(Student.tenant_id == user.tenant_id).all()
    grade_of = {s.id: s.grade_level for s in students}
    all_rows = db.query(StudentAssessment).filter(
        StudentAssessment.tenant_id == user.tenant_id).all()
    rows_by_grade = defaultdict(list)
    for a in all_rows:
        rows_by_grade[grade_of.get(a.student_id, "")].append(a)

    grades = ["K", "1", "2", "3"]

    def grade_block(rows, sids):
        fast_math = _pct_l3_by_period(rows, "FAST", "MATH", FAST_PERIODS)
        fast_ela = _pct_l3_by_period(rows, "FAST", "ELA", FAST_PERIODS)
        iready_math = _pct_l3_by_period(rows, "IREADY", "MATH", IREADY_PERIODS)
        fm_latest = _latest_level(rows, "FAST", "MATH", FAST_PERIODS)
        im_latest = _latest_level(rows, "IREADY", "MATH", IREADY_PERIODS)
        both = sum(1 for sid in sids
                   if (fm_latest.get(sid) or 0) >= 3 and (im_latest.get(sid) or 0) >= 3)
        return {
            "students": len(sids),
            "fast_math": fast_math, "fast_ela": fast_ela,
            "iready_math": iready_math,
            "goal_both_pct": round(100 * both / len(sids)) if sids else 0,
            "goal_both_n": both,
        }

    by_grade = {}
    for g in grades:
        sids = {s.id for s in students if s.grade_level == g}
        if not sids:
            continue
        by_grade[g] = grade_block(rows_by_grade.get(g, []), sids)

    tested_sids = {s.id for s in students if s.grade_level in grades}
    school = grade_block(
        [a for a in all_rows if grade_of.get(a.student_id) in grades], tested_sids)
    return {"school": school, "by_grade": by_grade,
            "goal": "Level 3+ in BOTH FAST Math and i-Ready Math"}


@router.get("/overview")
def overview(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """School-wide FAST Math/ELA proficiency by grade (latest period available)."""
    students = db.query(Student).filter(Student.tenant_id == user.tenant_id).all()
    sid_grade = {s.id: s.grade_level for s in students}
    rows = db.query(StudentAssessment).filter(
        StudentAssessment.tenant_id == user.tenant_id).all()
    grade_rows = defaultdict(list)
    for a in rows:
        grade_rows[sid_grade.get(a.student_id, "")].append(a)
    result = {}
    for g in ["K", "1", "2", "3"]:
        gr = grade_rows.get(g, [])
        if not gr:
            continue
        result[g] = {
            "students": sum(1 for s in students if s.grade_level == g),
            "fast_math": _fast_summary(gr, "MATH"),
            "fast_ela": _fast_summary(gr, "ELA"),
        }
    return {"by_grade": result}


def _students_for_teacher(db, tenant_id, teacher_id):
    class_ids = [c.id for c in db.query(ClassRoom).filter(
        ClassRoom.tenant_id == tenant_id,
        ClassRoom.teacher_id == teacher_id).all()]
    if not class_ids:
        return []
    sids = {r[0] for r in db.query(Enrollment.student_id).filter(
        Enrollment.class_id.in_(class_ids)).all()}
    return db.query(Student).filter(Student.id.in_(sids)).all() if sids else []


@router.get("/teachers")
def teachers(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List teachers with their student counts and FAST Math proficiency."""
    tlist = db.query(User).filter(
        User.tenant_id == user.tenant_id, User.role == "teacher").all()
    # latest FAST Math level per student
    latest = {}
    for a in db.query(StudentAssessment).filter(
            StudentAssessment.tenant_id == user.tenant_id,
            StudentAssessment.source == "FAST",
            StudentAssessment.subject == "MATH").all():
        if a.level is None or not (1 <= a.level <= 5):
            continue
        order = FAST_PERIODS.index(a.period) if a.period in FAST_PERIODS else -1
        cur = latest.get(a.student_id)
        if cur is None or order > cur[0]:
            latest[a.student_id] = (order, int(a.level), a.period)
    out = []
    for t in tlist:
        students = _students_for_teacher(db, user.tenant_id, t.id)
        if not students:
            continue
        grades = sorted({s.grade_level for s in students})
        levels = [latest[s.id][1] for s in students if s.id in latest]
        period = next((latest[s.id][2] for s in students if s.id in latest), None)
        out.append({
            "teacher_id": t.id, "name": t.name, "grades": grades,
            "students": len(students),
            "tested": len(levels),
            "fast_math_period": period,
            "asd": bool((t.scope or {}).get("asd")),
            "pct_level_3_plus": round(100 * sum(1 for x in levels if x >= 3) / len(levels))
                                if levels else None,
        })
    out.sort(key=lambda x: (x["grades"], x["name"]))
    # Diagnostics so the UI can explain an empty list (helps triage "no data by
    # teacher": are there teachers/classes/enrollments at all?).
    total_teachers = len(tlist)
    total_classes = db.query(ClassRoom).filter(
        ClassRoom.tenant_id == user.tenant_id).count()
    total_enroll = (db.query(Enrollment)
                    .join(ClassRoom, Enrollment.class_id == ClassRoom.id)
                    .filter(ClassRoom.tenant_id == user.tenant_id).count())
    if not out:
        if total_teachers == 0:
            diag = ("No teachers found. Upload a Class Lists workbook (sheets "
                    "named '<class code> - <Teacher>') or a roster CSV with a "
                    "teacher column on the Coach page.")
        elif total_enroll == 0:
            diag = (f"{total_teachers} teachers exist but no students are linked "
                    "to a class. Upload the Class Lists workbook so students are "
                    "enrolled in a teacher's class.")
        else:
            diag = ("Teachers and classes exist but none matched. Try re-importing "
                    "the Class Lists workbook.")
    else:
        diag = None
    return {
        "teachers": out,
        "diagnostics": {
            "total_teachers": total_teachers,
            "teachers_with_students": len(out),
            "total_classes": total_classes,
            "total_enrollments": total_enroll,
            "message": diag,
        },
    }


# Grades the school actually has: Pre-K through 3rd. Grade 4+ signals a bad import.
@router.post("/teachers/{teacher_id}/asd")
def set_teacher_asd(
    teacher_id: str,
    asd: bool = Body(..., embed=True),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Mark (or unmark) a teacher's class as ASD, saved on the teacher so their DI
    packets always get autism-friendly supports on any device — no per-generation
    checkbox needed."""
    t = db.get(User, teacher_id)
    if not t or t.tenant_id != user.tenant_id or t.role != "teacher":
        raise HTTPException(404, "Teacher not found")
    sc = dict(t.scope or {})
    sc["asd"] = bool(asd)
    t.scope = sc
    db.add(t)
    db.commit()
    return {"teacher_id": t.id, "name": t.name, "asd": sc["asd"]}


EXPECTED_GRADES = ["PK", "K", "1", "2", "3"]


@router.get("/roster-audit")
def roster_audit(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Data-quality check across every teacher: grade(s) taught, roster size,
    how many students actually have a FAST Math score (coverage), and anomalies
    — students on a grade the school doesn't have (e.g. Grade 4), and teachers
    whose roster spans more than one grade. Lets a coach verify the whole roster
    at a glance and catch bad imports."""
    expected = set(EXPECTED_GRADES)
    # latest FAST Math level per student (same rule as the teachers list)
    latest: dict = {}
    for a in db.query(StudentAssessment).filter(
            StudentAssessment.tenant_id == user.tenant_id,
            StudentAssessment.source == "FAST",
            StudentAssessment.subject == "MATH").all():
        if a.level is None or not (1 <= a.level <= 5):
            continue
        order = FAST_PERIODS.index(a.period) if a.period in FAST_PERIODS else -1
        cur = latest.get(a.student_id)
        if cur is None or order > cur[0]:
            latest[a.student_id] = (order, int(a.level))

    tlist = db.query(User).filter(
        User.tenant_id == user.tenant_id, User.role == "teacher").all()
    teachers = []
    off_grade: list = []
    seen_off: set = set()
    for t in tlist:
        students = _students_for_teacher(db, user.tenant_id, t.id)
        if not students:
            continue
        grades = sorted({s.grade_level for s in students})
        tested = [s for s in students if s.id in latest]
        bad = sorted({s.grade_level for s in students
                      if (s.grade_level or "") not in expected})
        for s in students:
            g = s.grade_level or ""
            if g not in expected and s.id not in seen_off:
                seen_off.add(s.id)
                off_grade.append({
                    "student": f"{s.first_name.title()} {s.last_name.title()}",
                    "grade": g or "(blank)", "teacher": t.name})
        teachers.append({
            "teacher_id": t.id, "name": t.name, "grades": grades,
            "asd": bool((t.scope or {}).get("asd")),
            "students": len(students),
            "tested": len(tested),
            "coverage_pct": round(100 * len(tested) / len(students)) if students else 0,
            "pct_level_3_plus": (round(100 * sum(1 for s in tested if latest[s.id][1] >= 3)
                                       / len(tested)) if tested else None),
            "multi_grade": len(grades) > 1,
            "off_grade": bad,
        })
    teachers.sort(key=lambda x: (x["coverage_pct"], x["name"]))
    # School-wide grade counts, so an unexpected grade is obvious.
    all_students = db.query(Student).filter(
        Student.tenant_id == user.tenant_id).all()
    grade_counts: dict = {}
    for s in all_students:
        g = s.grade_level or "(blank)"
        grade_counts[g] = grade_counts.get(g, 0) + 1
    return {
        "expected_grades": EXPECTED_GRADES,
        "grade_counts": dict(sorted(grade_counts.items())),
        "off_grade_students": sorted(off_grade, key=lambda x: (x["grade"], x["teacher"])),
        "teachers": teachers,
    }


def _l25_ids(db, tenant_id, grade):
    """Lowest-25% student ids in a grade, by latest FAST Math scale (fallback
    level). Computed automatically instead of relying on a manual flag column."""
    students = db.query(Student).filter(
        Student.tenant_id == tenant_id, Student.grade_level == grade).all()
    sids = {s.id for s in students}
    best = {}
    for a in db.query(StudentAssessment).filter(
            StudentAssessment.tenant_id == tenant_id,
            StudentAssessment.source == "FAST",
            StudentAssessment.subject == "MATH").all():
        if a.student_id not in sids:
            continue
        order = FAST_PERIODS.index(a.period) if a.period in FAST_PERIODS else -1
        metric = a.scale_score if a.scale_score is not None else (
            a.level if a.level and 1 <= a.level <= 5 else None)
        if metric is None:
            continue
        cur = best.get(a.student_id)
        if cur is None or order > cur[0]:
            best[a.student_id] = (order, metric)
    if not best:
        # No FAST Math for this grade yet — rank by topic-assessment average so
        # the lowest-25% flag still works from whatever data is loaded.
        topic_avgs: dict = {}
        for a in db.query(StudentAssessment).filter(
                StudentAssessment.tenant_id == tenant_id,
                StudentAssessment.source == "TOPIC",
                StudentAssessment.subject == "MATH").all():
            if a.student_id not in sids or a.percent is None:
                continue
            topic_avgs.setdefault(a.student_id, []).append(a.percent)
        if not topic_avgs:
            return set()
        ranked = sorted(((sid, sum(v) / len(v)) for sid, v in topic_avgs.items()),
                        key=lambda kv: kv[1])
        cutoff = max(1, round(len(ranked) * 0.25))
        return {sid for sid, _ in ranked[:cutoff]}
    ranked = sorted(best.items(), key=lambda kv: kv[1][1])
    cutoff = max(1, round(len(ranked) * 0.25))
    return {sid for sid, _ in ranked[:cutoff]}


@router.get("/teacher/{teacher_id}")
def teacher_report(
    teacher_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Combined master tracker for a teacher's roster — unions everything from
    the Class Lists and the Topic Tracker: demographics, FAST ELA + Math
    (PM1/2/3), iReady ELA + Math (AP1/2), every Topic assessment, topic average,
    plus computed on-track (Level 3+) and lowest-25% flags."""
    teacher = db.get(User, teacher_id)
    students = _students_for_teacher(db, user.tenant_id, teacher_id)
    sids = {s.id for s in students}
    rows_a = [a for a in db.query(StudentAssessment).filter(
        StudentAssessment.tenant_id == user.tenant_id).all()
        if a.student_id in sids]

    def blank():
        return {"fast_ela": {}, "fast_math": {}, "iready_ela": {},
                "iready_math": {}, "topics": {}}
    data = defaultdict(blank)
    topic_periods = set()
    for a in rows_a:
        d = data[a.student_id]
        lvl = int(a.level) if (a.level is not None and 1 <= a.level <= 5) else a.level
        if a.source == "FAST" and a.subject == "ELA" and lvl is not None:
            d["fast_ela"][a.period] = lvl
        elif a.source == "FAST" and a.subject == "MATH" and lvl is not None:
            d["fast_math"][a.period] = lvl
        elif a.source == "IREADY" and a.subject == "ELA" and a.level is not None:
            d["iready_ela"][a.period] = int(a.level)
        elif a.source == "IREADY" and a.subject == "MATH" and a.level is not None:
            d["iready_math"][a.period] = int(a.level)
        elif a.source == "TOPIC" and a.percent is not None:
            d["topics"][a.period] = round(100 * a.percent)
            topic_periods.add(a.period)

    def tp_order(p):
        m = re.search(r"\d+", p)
        return int(m.group()) if m else 99
    topic_cols = sorted(topic_periods, key=tp_order)

    grades = {s.grade_level for s in students}
    l25 = set()
    for g in grades:
        l25 |= _l25_ids(db, user.tenant_id, g)

    roster = []
    for s in students:
        d = data.get(s.id, blank())
        tvals = list(d["topics"].values())
        topic_avg = round(sum(tvals) / len(tvals)) if tvals else None
        latest = None
        for p in reversed(FAST_PERIODS):
            v = d["fast_math"].get(p)
            if isinstance(v, int) and 1 <= v <= 5:
                latest = v
                break
        # Level 3+ from the latest FAST Math when it exists; otherwise fall back
        # to the topic-assessment average (so a class with only topic scores
        # loaded isn't shown as 0% Level 3+ with everyone flagged).
        if latest is not None:
            on_track = latest >= 3
        elif topic_avg is not None:
            tl = topic_level(s.grade_level, topic_avg)
            on_track = tl is not None and tl >= 3
        else:
            on_track = False
        roster.append({
            "student_id": s.id, "name": f"{s.first_name.title()} {s.last_name.title()}",
            "grade": s.grade_level,
            "ell": (s.flags or {}).get("ell"), "ese": bool((s.flags or {}).get("ese")),
            "fast_ela": d["fast_ela"], "fast_math": d["fast_math"],
            "iready_ela": d["iready_ela"], "iready_math": d["iready_math"],
            "topics": d["topics"], "topic_avg": topic_avg,
            "on_track": on_track,
            "l25": s.id in l25,
        })
    roster.sort(key=lambda r: r["name"])
    prof = sum(1 for r in roster if r["on_track"])
    return {
        "teacher": teacher.name if teacher else "",
        "students": len(roster),
        "pct_level_3_plus": round(100 * prof / len(roster)) if roster else 0,
        "topic_columns": topic_cols,
        "roster": roster,
    }


@router.get("/fast/{grade}")
def fast_analysis(
    grade: str,
    subject: str = "MATH",
    period: str = "PM1",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Expert FAST item analysis for a grade: overall, by domain, by benchmark
    (focus standards), by student, plus target students for growth to Level 3+.
    """
    subject, period = subject.upper(), period.upper()
    students = db.query(Student).filter(
        Student.tenant_id == user.tenant_id, Student.grade_level == grade).all()
    sids = {s.id for s in students}
    name = {s.id: f"{s.first_name.title()} {s.last_name.title()}" for s in students}

    items = [r for r in db.query(StudentBenchmarkResult).filter(
        StudentBenchmarkResult.tenant_id == user.tenant_id,
        StudentBenchmarkResult.subject == subject,
        StudentBenchmarkResult.period == period).all() if r.student_id in sids]
    summ = [a for a in db.query(StudentAssessment).filter(
        StudentAssessment.tenant_id == user.tenant_id,
        StudentAssessment.source == "FAST",
        StudentAssessment.subject == subject,
        StudentAssessment.period == period).all() if a.student_id in sids]

    if not items and not summ:
        return {"grade": grade, "subject": subject, "period": period,
                "has_data": False}

    # Overall + level distribution.
    levels = [int(a.level) for a in summ if a.level is not None]
    dist = {str(i): levels.count(i) for i in range(1, 6)}
    l3 = sum(1 for x in levels if x >= 3)
    tot_e = sum(r.points_earned for r in items)
    tot_p = sum(r.points_possible for r in items) or 1

    # By domain (category) and by benchmark.
    dom = defaultdict(lambda: [0.0, 0.0])
    bench = defaultdict(lambda: [0.0, 0.0])
    for r in items:
        dom[r.category][0] += r.points_earned
        dom[r.category][1] += r.points_possible
        bench[r.benchmark_code][0] += r.points_earned
        bench[r.benchmark_code][1] += r.points_possible

    by_domain = sorted(
        [{"domain": k, "pct": round(100 * e / p), "points_possible": int(p)}
         for k, (e, p) in dom.items() if p],
        key=lambda x: x["pct"])
    std_desc = {s.code: s.description for s in db.query(Standard).all()}
    by_benchmark = sorted(
        [{"benchmark": k, "pct": round(100 * e / p),
          "n": int(p), "description": std_desc.get(k, "")}
         for k, (e, p) in bench.items() if p],
        key=lambda x: x["pct"])

    # Per student: total %, benchmarks assessed, level, domain %s.
    per_student_items = defaultdict(lambda: [0.0, 0.0, 0])
    per_student_dom = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    for r in items:
        ps = per_student_items[r.student_id]
        ps[0] += r.points_earned
        ps[1] += r.points_possible
        ps[2] += 1
        d = per_student_dom[r.student_id][r.category]
        d[0] += r.points_earned
        d[1] += r.points_possible
    level_of = {a.student_id: a.level for a in summ}
    scale_of = {a.student_id: a.scale_score for a in summ}
    per_student = []
    for sid in sids:
        e, p, n = per_student_items.get(sid, [0, 0, 0])
        per_student.append({
            "student_id": sid, "name": name.get(sid, ""),
            "level": level_of.get(sid), "scale_score": scale_of.get(sid),
            "benchmarks_assessed": n,
            "percent_score": round(100 * e / p) if p else None,
            "domain_pct": {k: round(100 * de / dp) if dp else None
                           for k, (de, dp) in per_student_dom.get(sid, {}).items()},
        })
    per_student.sort(key=lambda x: (x["percent_score"] is None, x["percent_score"] or 0))

    # Target students: Level 2 closest to Level 3 (bubble), then lowest Level 1.
    bubble = sorted(
        [p for p in per_student if p["level"] == 2],
        key=lambda x: -(x["scale_score"] or 0))
    lowest = [p for p in per_student if p["level"] == 1][:15]

    # Standards BY ACHIEVEMENT LEVEL: for students at each level, which
    # benchmarks they were tested on most, and which they're weakest on (the
    # standards to master to advance to the next level).
    level_bench = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    for r in items:
        lv = level_of.get(r.student_id)
        if lv is None or not (1 <= lv <= 5):
            continue
        lb = level_bench[int(lv)][r.benchmark_code]
        lb[0] += r.points_earned
        lb[1] += r.points_possible
    by_level = {}
    for lv, benches in sorted(level_bench.items()):
        rows_b = [{"benchmark": k, "pct": round(100 * e / p), "tested": int(p),
                   "description": std_desc.get(k, "")}
                  for k, (e, p) in benches.items() if p]
        n = sum(1 for s, l in level_of.items() if l == lv and s in sids)
        by_level[str(lv)] = {
            "n_students": n,
            "next_level": lv + 1 if lv < 5 else None,
            "mostly_tested": sorted(rows_b, key=lambda x: -x["tested"])[:8],
            "focus_to_advance": sorted(rows_b, key=lambda x: x["pct"])[:8],
        }

    # Combined goal: Level 3+ in BOTH FAST and i-Ready (Math).
    iready_level = {}
    for a in db.query(StudentAssessment).filter(
            StudentAssessment.tenant_id == user.tenant_id,
            StudentAssessment.source == "IREADY",
            StudentAssessment.subject == subject).all():
        if a.student_id not in sids or a.level is None:
            continue
        order = IREADY_PERIODS.index(a.period) if a.period in IREADY_PERIODS else -1
        cur = iready_level.get(a.student_id)
        if cur is None or order > cur[0]:
            iready_level[a.student_id] = (order, a.level)
    both = sum(1 for sid in sids
               if (level_of.get(sid) or 0) >= 3
               and (iready_level.get(sid, (0, 0))[1] or 0) >= 3)
    iready_prof = sum(1 for sid in sids if (iready_level.get(sid, (0, 0))[1] or 0) >= 3)

    return {
        "grade": grade, "subject": subject, "period": period, "has_data": True,
        "overall": {
            "students": len(students),
            "students_tested": len(levels),
            "overall_pct_correct": round(100 * tot_e / tot_p, 1),
            "level_distribution": dist,
            "pct_level_3_plus": round(100 * l3 / len(levels)) if levels else 0,
            "pct_iready_level_3_plus": round(100 * iready_prof / len(sids)) if sids else 0,
            "pct_goal_both": round(100 * both / len(sids)) if sids else 0,
            "avg_scale_score": round(sum(a.scale_score for a in summ
                                     if a.scale_score) / max(1, len(summ))),
            "goal": "Level 3+ in BOTH FAST and i-Ready",
        },
        "by_domain": by_domain,
        "by_benchmark": by_benchmark,
        "focus_standards": by_benchmark[:8],
        "by_level": by_level,
        "per_student": per_student,
        "target_students": {
            "bubble_level2": bubble[:15],
            "lowest_level1": lowest,
        },
    }


@router.get("/grade/{grade}")
def grade_report(
    grade: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Detailed performance report for one grade."""
    students = db.query(Student).filter(
        Student.tenant_id == user.tenant_id,
        Student.grade_level == grade).all()
    sids = {s.id for s in students}
    rows = [a for a in db.query(StudentAssessment).filter(
        StudentAssessment.tenant_id == user.tenant_id).all()
        if a.student_id in sids]

    # Lowest-25%: by latest available FAST Math level, then topic average.
    latest_math = {}
    topic_avg = defaultdict(list)
    for a in rows:
        if a.source == "FAST" and a.subject == "MATH" and _is_level(a.level):
            cur = latest_math.get(a.student_id)
            order = FAST_PERIODS.index(a.period) if a.period in FAST_PERIODS else -1
            if cur is None or order > cur[0]:
                latest_math[a.student_id] = (order, int(a.level))
        if a.source == "TOPIC" and a.percent is not None:
            topic_avg[a.student_id].append(a.percent)

    name = {s.id: f"{s.first_name.title()} {s.last_name.title()}" for s in students}

    # Homeroom teacher per student (via the HOMEROOM class enrollment).
    hr_classes = {c.id: c for c in db.query(ClassRoom).filter(
        ClassRoom.tenant_id == user.tenant_id).all()}
    teacher_name = {u.id: u.name for u in db.query(User).filter(
        User.tenant_id == user.tenant_id, User.role == "teacher").all()}
    stu_teacher = {}
    if sids:
        for e in db.query(Enrollment).filter(Enrollment.student_id.in_(sids)).all():
            c = hr_classes.get(e.class_id)
            if c and e.student_id not in stu_teacher:
                stu_teacher[e.student_id] = teacher_name.get(c.teacher_id, "")

    watch = []
    roster = []
    for s in students:
        sid = s.id
        lvl = latest_math.get(sid, (None, None))[1]
        tavg = (sum(topic_avg[sid]) / len(topic_avg[sid])) if topic_avg.get(sid) else None
        f = s.flags or {}
        entry = {
            "student_id": sid, "name": name.get(sid, ""),
            "teacher": stu_teacher.get(sid, "—"),
            "fast_math_level": lvl,
            "topic_avg": round(100 * tavg) if tavg is not None else None,
            "ell": bool(f.get("ell")), "ese": bool(f.get("ese")),
        }
        roster.append(entry)
        if (lvl is not None and lvl < 3) or (tavg is not None and tavg < 0.6):
            watch.append(entry)
    roster.sort(key=lambda r: r["name"])
    watch.sort(key=lambda x: (x["fast_math_level"] or 9, x["topic_avg"] or 100))

    return {
        "grade": grade,
        "students": len(students),
        "fast_math": _fast_summary(rows, "MATH"),
        "fast_ela": _fast_summary(rows, "ELA"),
        "iready_math": _iready_summary(rows, "MATH"),
        "iready_ela": _iready_summary(rows, "ELA"),
        "topic_assessments": _topic_summary(rows),
        "roster": roster,
        "watchlist": watch[:40],
        "watchlist_count": len(watch),
    }


def _goal_analysis_data(db, tenant_id, grade):
    from app.goal_rubric import evaluate, project, topic_color

    class _U:
        pass
    user = _U()
    user.tenant_id = tenant_id

    students = db.query(Student).filter(
        Student.tenant_id == user.tenant_id, Student.grade_level == grade).all()
    sids = {s.id for s in students}
    name = {s.id: f"{s.first_name.title()} {s.last_name.title()}" for s in students}
    rows = [a for a in db.query(StudentAssessment).filter(
        StudentAssessment.tenant_id == user.tenant_id).all() if a.student_id in sids]

    order = FAST_REPORT_PERIODS  # Baseline, PM1, PM2, PM3
    per = {}
    for a in rows:
        d = per.setdefault(a.student_id,
                           {"scale": {}, "level": {}, "topics": [], "iready": {}})
        if a.source == "FAST" and a.subject == "MATH":
            if a.scale_score is not None:
                d["scale"][a.period] = a.scale_score
            if a.level is not None and 1 <= a.level <= 5:
                d["level"][a.period] = int(a.level)
        elif a.source == "IREADY" and a.subject == "MATH" and a.level is not None:
            if 1 <= a.level <= 5:
                d["iready"][a.period] = int(a.level)
        elif a.source == "TOPIC" and a.percent is not None:
            d["topics"].append(a.percent)

    def latest(m):
        for p in reversed(order):
            if p in m:
                return m[p]
        return None

    def latest_iready(m):
        """Most recent i-Ready level (AP2 over AP1, etc.)."""
        if not m:
            return None
        def ap(p):
            mm = re.search(r"\d+", p)
            return int(mm.group()) if mm else 0
        return m[max(m, key=ap)]

    out = []
    summary = {"students": len(students), "with_fast": 0, "meeting": 0,
               "below": 0, "above": 0, "projected_goal": 0, "disagreements": 0}
    for s in students:
        d = per.get(s.id, {"scale": {}, "level": {}, "topics": [], "iready": {}})
        scale = latest(d["scale"])
        topic_avg = round(100 * sum(d["topics"]) / len(d["topics"])) if d["topics"] else None
        ev = evaluate(grade, scale, topic_avg)
        pr = project(grade, d["level"], topic_avg)
        tc = topic_color(grade, topic_avg)
        if scale is not None:
            summary["with_fast"] += 1

        # Triangulation: each measure's own level, side by side, with a flag when
        # they disagree (the coach establishes the "real" level from all three).
        fast_lvl = latest(d["level"])
        iready_lvl = latest_iready(d["iready"])
        topic_lvl = tc["level"] if tc else None
        present = [x for x in (fast_lvl, iready_lvl, topic_lvl) if x is not None]
        level_gap = (max(present) - min(present)) if len(present) >= 2 else 0
        level_disagree = level_gap >= 1
        if level_disagree:
            summary["disagreements"] += 1
        if ev["status"] in ("meeting", "above"):
            summary[ev["status"]] += 1
        elif ev["status"] == "below":
            summary["below"] += 1
        if pr["projected_level_3_plus"]:
            summary["projected_goal"] += 1
        out.append({
            "student_id": s.id, "name": name[s.id],
            "fast_scale": scale, "fast_level": ev["level"],
            "instructional": ev["instructional"],
            "goal_min": ev["goal_min"], "goal_max": ev["goal_max"],
            "topic_avg": topic_avg, "status": ev["status"], "gap": ev["gap"],
            "topic_level": tc["level"] if tc else None,
            "topic_color": tc["color"] if tc else None,
            "topic_hex": tc["hex"] if tc else None,
            "fast_only_level": fast_lvl, "iready_level": iready_lvl,
            "levels": {"fast": fast_lvl, "iready": iready_lvl, "topic": topic_lvl},
            "level_disagree": level_disagree, "level_gap": level_gap,
            "meets_school_goal": ev["meets_school_goal"],
            "trend": pr["trend"], "projected": pr["projected_level_3_plus"],
            "projection_note": pr["rationale"],
        })
    out.sort(key=lambda r: (r["status"] != "below", r["name"]))

    items = [r for r in db.query(StudentBenchmarkResult).filter(
        StudentBenchmarkResult.tenant_id == user.tenant_id,
        StudentBenchmarkResult.subject == "MATH").all() if r.student_id in sids]
    std_desc = {s.code: s.description for s in db.query(Standard).all()}
    cov = {}
    for r in items:
        c = cov.setdefault(r.benchmark_code, {"periods": set(), "items": 0,
                                              "earned": 0.0, "possible": 0.0})
        c["periods"].add(r.period)
        c["items"] += 1
        c["earned"] += r.points_earned
        c["possible"] += r.points_possible
    coverage = sorted(
        [{"benchmark": k, "description": std_desc.get(k, ""),
          "times_assessed": len(v["periods"]), "questions": v["items"],
          "avg_pct": round(100 * v["earned"] / v["possible"]) if v["possible"] else None}
         for k, v in cov.items()],
        key=lambda x: (x["avg_pct"] if x["avg_pct"] is not None else 999))

    return {"grade": grade, "students": out, "summary": summary,
            "benchmark_coverage": coverage, "has_fast": summary["with_fast"] > 0}


@router.get("/goal-analysis/{grade}")
def goal_analysis(
    grade: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """FAST↔Topic goal analysis for a grade, from the Math Goal Setting Rubric:
    each student's FAST-based topic goal, actual topic average, the topic level +
    color code (L1 Red … L5 Orange), and an end-of-year projection toward Level
    3+, plus benchmark coverage."""
    return _goal_analysis_data(db, user.tenant_id, grade)


@router.get("/goal-analysis/{grade}.xlsx")
def goal_analysis_xlsx(
    grade: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Download the goal analysis as a color-coded Excel report (topic-average
    cells shaded by achievement level)."""
    from fastapi import Response
    from app.export_xlsx import goal_analysis_to_xlsx
    data = _goal_analysis_data(db, user.tenant_id, grade)
    xlsx = goal_analysis_to_xlsx(data)
    fname = f"MathGoalAnalysis_Grade{grade}.xlsx"
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})
