"""M-DCPS Framework of Effective Instruction — the coaching lens.

Loads the six components (with expert, math-specific elaboration) and provides a
year-long weekly focus so each week leads with one component. `current_week_focus`
maps today's date to the school week and its focus."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

_DATA = Path(__file__).parent / "data" / "framework.json"

# First instructional day of the 2026-2027 year (from the district calendar).
SCHOOL_YEAR_START = "2026-08-13"

# A 36-week arc: each week leads with one component. The rhythm front-loads
# environment & planning, anchors Assessment to the FAST/i-Ready windows, and
# spirals delivery/engagement/knowledge-of-learners throughout.
WEEKLY_FOCUS = [
    (1, "learning_environment", "Launch the math community", "Set routines, norms, and a 'mistakes are thinking' culture from day one."),
    (2, "instructional_planning", "Unpack Topic 1 for rigor", "Plan backward from the ALD Level 3 and the exit ticket."),
    (3, "knowledge_of_learners", "Know every entry point", "Use baseline data to see who needs access, on-grade, or stretch."),
    (4, "assessment", "Baseline → first DI groups", "FAST PM1 / i-Ready AP1 data forms your first differentiated groups."),
    (5, "instructional_delivery", "Model the thinking (I Do)", "Make math reasoning visible; concrete first in the CPA sequence."),
    (6, "engagement", "Math discourse & talk", "Sentence frames and Rally Coach so every student explains."),
    (7, "instructional_planning", "Topic 2 + pacing check", "Re-plan from data; keep the plan aligned to the benchmark."),
    (8, "knowledge_of_learners", "Differentiate on purpose", "One benchmark at three complexity levels; ELL/ESE scaffolds."),
    (9, "instructional_delivery", "Questioning across DOK", "Plan DOK 1–3 questions; mine wrong answers for reasoning."),
    (10, "assessment", "Formative → reteach loop", "Topic assessments drive same-day reteach and enrichment."),
    (11, "engagement", "Collaborative structures", "Numbered Heads / Team Huddle with clear partner roles."),
    (12, "learning_environment", "High expectations for all", "Voice high expectations for every group; protect productive struggle."),
    (13, "instructional_planning", "Mid-year pacing recalibration", "Adjust the map to reality without dropping rigor."),
    (14, "assessment", "PM2 progress monitoring", "FAST PM2 / i-Ready AP2 — measure movement toward Level 3+."),
    (15, "knowledge_of_learners", "Target the bubble (L2→L3)", "Name the exact gap for near-proficient students and close it."),
    (16, "instructional_delivery", "CUBS & word-problem reasoning", "Understand the story before choosing an operation."),
    (17, "engagement", "Authentic, real-world tasks", "Connect the benchmark to contexts students care about."),
    (18, "instructional_planning", "Design for Level-3 rigor", "Every task pointed at the on-grade ALD."),
    (19, "learning_environment", "Feedback culture", "Students receive and act on specific feedback."),
    (20, "assessment", "Student data chats", "Learners track and own their own growth toward the goal."),
    (21, "knowledge_of_learners", "Refine DI groups", "Regroup from current evidence; groups are fluid, not fixed."),
    (22, "instructional_delivery", "Gradual-release fidelity", "ACES done right — students do progressively more thinking."),
    (23, "engagement", "CPA & manipulatives daily", "Models in students' hands, not just on the camera."),
    (24, "instructional_planning", "Spiral & mixed practice", "Interleave prior standards so mastery sticks."),
    (25, "assessment", "PM3 readiness audit", "Standards-mastery check ahead of the final window."),
    (26, "knowledge_of_learners", "Enrichment for L4–L5", "Depth and reasoning, not just more problems."),
    (27, "instructional_delivery", "Precision of vocabulary", "Academic language modeled and required back from students."),
    (28, "engagement", "Explain & justify (MTR 4.1)", "Reasoning out loud is the norm for every student."),
    (29, "learning_environment", "Independence & self-regulation", "Students manage materials, time, and their own learning."),
    (30, "assessment", "PM3 / AP3 analysis", "Final push — analyze and act on the last data of the year."),
    (31, "instructional_planning", "Plan targeted reteach", "Use results to plan the highest-impact reteaching."),
    (32, "instructional_delivery", "Close the gaps", "Precise, high-impact reteaching for the students who need it."),
    (33, "knowledge_of_learners", "Personalize & celebrate growth", "Honor movement; personalize the last stretch."),
    (34, "engagement", "Culminating math tasks", "Rich tasks that show off reasoning and application."),
    (35, "assessment", "Year-end reflection", "What actually moved the goal — name it to repeat it."),
    (36, "instructional_planning", "Vertical planning / hand-off", "Set up next grade's teachers for a strong start."),
]


def load_framework() -> dict:
    return json.loads(_DATA.read_text())


def component_map() -> dict:
    return {c["key"]: c for c in load_framework()["components"]}


def _school_week(today: date, year_start: date) -> int:
    if today < year_start:
        return 1
    return min(36, (today - year_start).days // 7 + 1)


def week_focus(week: int) -> dict:
    """The lens/focus for a given school week number (1-36)."""
    week = max(1, min(36, week))
    wk, key, focus, why = WEEKLY_FOCUS[week - 1]
    comp = component_map().get(key, {})
    return {
        "week": wk,
        "component_key": key,
        "component_name": comp.get("name", key),
        "focus": focus,
        "why": why,
        "essence": comp.get("essence", ""),
    }


def current_week_focus(today_iso: str | None = None,
                       year_start_iso: str = SCHOOL_YEAR_START) -> dict:
    """The framework lens for THIS school week (what teachers are teaching now)."""
    today = date.fromisoformat(today_iso) if today_iso else date.today()
    ys = date.fromisoformat(year_start_iso)
    return week_focus(_school_week(today, ys))


def planning_week_focus(today_iso: str | None = None,
                        year_start_iso: str = SCHOOL_YEAR_START) -> dict:
    """The framework lens for NEXT school week — what this week's planning
    meetings are actually about (coaches plan a week ahead)."""
    today = date.fromisoformat(today_iso) if today_iso else date.today()
    ys = date.fromisoformat(year_start_iso)
    return week_focus(_school_week(today, ys) + 1)
