"""Grade-level performance analytics — the goal-tracking reports built from
imported FAST / iReady / Topic assessment data."""
from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user
from app.models import (
    Standard,
    Student,
    StudentAssessment,
    StudentBenchmarkResult,
    User,
)

router = APIRouter(prefix="/reports", tags=["reports"])

# FAST achievement levels are 1-5; level >= 3 is proficient.
FAST_PERIODS = ["PM1", "PM2", "PM3"]
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
    for p in FAST_PERIODS:
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

    return {
        "grade": grade, "subject": subject, "period": period, "has_data": True,
        "overall": {
            "students": len(students),
            "students_tested": len(levels),
            "overall_pct_correct": round(100 * tot_e / tot_p, 1),
            "level_distribution": dist,
            "pct_level_3_plus": round(100 * l3 / len(levels)) if levels else 0,
            "avg_scale_score": round(sum(a.scale_score for a in summ
                                     if a.scale_score) / max(1, len(summ))),
            "goal": "All students Level 3+ by PM3",
        },
        "by_domain": by_domain,
        "by_benchmark": by_benchmark,
        "focus_standards": by_benchmark[:8],
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
    watch = []
    for sid in sids:
        lvl = latest_math.get(sid, (None, None))[1]
        tavg = (sum(topic_avg[sid]) / len(topic_avg[sid])) if topic_avg.get(sid) else None
        if (lvl is not None and lvl < 3) or (tavg is not None and tavg < 0.6):
            watch.append({"student_id": sid, "name": name.get(sid, ""),
                          "fast_math_level": lvl,
                          "topic_avg": round(100 * tavg) if tavg is not None else None})
    watch.sort(key=lambda x: (x["fast_math_level"] or 9, x["topic_avg"] or 100))

    return {
        "grade": grade,
        "students": len(students),
        "fast_math": _fast_summary(rows, "MATH"),
        "fast_ela": _fast_summary(rows, "ELA"),
        "iready_math": _iready_summary(rows, "MATH"),
        "iready_ela": _iready_summary(rows, "ELA"),
        "topic_assessments": _topic_summary(rows),
        "watchlist": watch[:40],
        "watchlist_count": len(watch),
    }
