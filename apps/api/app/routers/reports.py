"""Grade-level performance analytics — the goal-tracking reports built from
imported FAST / iReady / Topic assessment data."""
from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user
from app.models import Student, StudentAssessment, User

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
