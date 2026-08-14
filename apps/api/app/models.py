"""ORM models — a portable, MVP subset of docs/07-database-schema.md.

Design choices for portability (SQLite locally, Postgres on Railway):
- String UUID primary keys (uuid4) instead of native UUID columns.
- Generic JSON type instead of Postgres JSONB.
Every student/school-scoped row carries tenant_id (district) so that
row-level scoping can be enforced consistently, per the RBAC design.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now
    )


# --- Organization & identity -------------------------------------------------

class District(Base, TimestampMixin):
    __tablename__ = "districts"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, default="FL")


class School(Base, TimestampMixin):
    __tablename__ = "schools"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    grade_range: Mapped[str] = mapped_column(String, default="K-5")


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    school_id: Mapped[str | None] = mapped_column(ForeignKey("schools.id"), nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, default="teacher")  # see ROLES
    # scope narrows what the user can see (grades, subjects, class ids, caseload)
    scope: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="active")


ROLES = [
    "district_admin", "principal", "ap", "reading_coach", "math_coach",
    "instructional_coach", "teacher", "interventionist", "ese_teacher",
    "ell_teacher", "support_staff",
]


# --- Students & classes -------------------------------------------------------

class Student(Base, TimestampMixin):
    __tablename__ = "students"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id"), index=True)
    district_student_id: Mapped[str] = mapped_column(String, index=True)
    first_name: Mapped[str] = mapped_column(String)
    last_name: Mapped[str] = mapped_column(String)
    grade_level: Mapped[str] = mapped_column(String)
    # program flags: {"ell": "L3", "ese": true, "504": false, "mtss_tier": 2}
    flags: Mapped[dict] = mapped_column(JSON, default=dict)


class ClassRoom(Base, TimestampMixin):
    __tablename__ = "classes"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id"), index=True)
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    subject: Mapped[str] = mapped_column(String)  # ELA | MATH
    grade_level: Mapped[str] = mapped_column(String)


class Enrollment(Base, TimestampMixin):
    __tablename__ = "enrollments"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    class_id: Mapped[str] = mapped_column(ForeignKey("classes.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)


# --- Standards ---------------------------------------------------------------

class Standard(Base, TimestampMixin):
    __tablename__ = "standards"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    framework: Mapped[str] = mapped_column(String, default="FL B.E.S.T.")
    subject: Mapped[str] = mapped_column(String)  # ELA | MATH
    grade_level: Mapped[str] = mapped_column(String)
    code: Mapped[str] = mapped_column(String, index=True)  # e.g. ELA.3.R.2.2
    description: Mapped[str] = mapped_column(Text)
    mastery_threshold: Mapped[float] = mapped_column(Float, default=0.7)
    details: Mapped[dict] = mapped_column(JSON, default=dict)  # targets, misconceptions...


# --- Assessments -------------------------------------------------------------

class AssessmentDefinition(Base, TimestampMixin):
    __tablename__ = "assessment_definitions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)  # FAST_PM1 | EXIT_TICKET | ...
    subject: Mapped[str] = mapped_column(String)
    grade_level: Mapped[str] = mapped_column(String)


class AssessmentResult(Base, TimestampMixin):
    __tablename__ = "assessment_results"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_definitions.id"), index=True
    )
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    standard_id: Mapped[str] = mapped_column(ForeignKey("standards.id"), index=True)
    percent_correct: Mapped[float] = mapped_column(Float)


class StandardMastery(Base, TimestampMixin):
    """Per student x standard current state — powers dashboards and grouping."""
    __tablename__ = "standard_mastery"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    standard_id: Mapped[str] = mapped_column(ForeignKey("standards.id"), index=True)
    mastery_pct: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String, default="not_started")
    # mastered | in_progress | deficient | not_started
    trend: Mapped[str] = mapped_column(String, default="flat")  # up | flat | down


# --- Differentiated instruction ----------------------------------------------

class DiGroup(Base, TimestampMixin):
    __tablename__ = "di_groups"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    class_id: Mapped[str] = mapped_column(ForeignKey("classes.id"), index=True)
    standard_id: Mapped[str] = mapped_column(ForeignKey("standards.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="draft")
    members: Mapped[list] = relationship(
        "DiGroupMember", cascade="all, delete-orphan", backref="group"
    )


class DiGroupMember(Base):
    __tablename__ = "di_group_members"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    di_group_id: Mapped[str] = mapped_column(ForeignKey("di_groups.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    added_by: Mapped[str] = mapped_column(String, default="system")  # system | teacher


# --- Compliance --------------------------------------------------------------

class AuditLog(Base):
    """Append-only record of student-data access (docs/00 guardrails)."""
    __tablename__ = "audit_log"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str | None] = mapped_column(String, nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(String)
    entity_type: Mapped[str] = mapped_column(String)
    entity_id: Mapped[str | None] = mapped_column(String, nullable=True)
    purpose: Mapped[str | None] = mapped_column(String, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)


# --- Curriculum & pacing (Collaborative Planning) ----------------------------

class PacingTopic(Base, TimestampMixin):
    """A topic/chapter on the district pacing calendar — the unit of a planning
    week. Mirrors the M-DCPS pacing guide structure (docs/G03 example)."""
    __tablename__ = "pacing_topics"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    subject: Mapped[str] = mapped_column(String)  # MATH | ELA
    grade_level: Mapped[str] = mapped_column(String, index=True)
    topic_code: Mapped[str] = mapped_column(String)   # e.g. "TOPIC IX"
    chapter: Mapped[str] = mapped_column(String, default="")   # e.g. "Chapter 9"
    name: Mapped[str] = mapped_column(String)         # "Understand Fractions"
    quarter: Mapped[str] = mapped_column(String, default="")   # nine-weeks label
    week_order: Mapped[int] = mapped_column(Integer, default=0)  # calendar order
    benchmarks: Mapped[list] = mapped_column(JSON, default=list)  # ["MA.3.FR.1.1", ...]
    learning_target: Mapped[str] = mapped_column(Text, default="")
    success_criteria: Mapped[list] = mapped_column(JSON, default=list)  # "I can..."
    vocabulary: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String, default="")
    # Quick Facts (from the collaborative planning guide format)
    time_frame: Mapped[str] = mapped_column(String, default="")
    topic_focus: Mapped[str] = mapped_column(Text, default="")
    ald_focus: Mapped[str] = mapped_column(String, default="")
    mtr_practices: Mapped[list] = mapped_column(JSON, default=list)
    materials: Mapped[list] = mapped_column(JSON, default=list)
    lessons: Mapped[list] = mapped_column(JSON, default=list)  # lesson outline


class StudentAssessment(Base, TimestampMixin):
    """Longitudinal assessment record — one row per student x assessment period.
    Covers FAST PM1/2/3, iReady AP1/2/3, Topic assessments (TP), and STAR.
    Value is stored as level (achievement level), scale_score, and/or percent,
    depending on the assessment."""
    __tablename__ = "student_assessments"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    source: Mapped[str] = mapped_column(String, index=True)   # FAST|IREADY|TOPIC|STAR
    subject: Mapped[str] = mapped_column(String, index=True)  # MATH|ELA
    period: Mapped[str] = mapped_column(String, index=True)   # PM1|PM2|PM3|AP1..|TP1..
    level: Mapped[float | None] = mapped_column(Float, nullable=True)
    scale_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    label: Mapped[str] = mapped_column(String, default="")   # original column label
    school_year: Mapped[str] = mapped_column(String, default="2025-2026")


class StudentBenchmarkResult(Base, TimestampMixin):
    """Item/benchmark-level result from a FAST item export — one row per
    student x test item, tagged with its B.E.S.T. benchmark. Enables analysis
    by benchmark, by domain (category), and by student."""
    __tablename__ = "student_benchmark_results"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    source: Mapped[str] = mapped_column(String, default="FAST")
    subject: Mapped[str] = mapped_column(String, index=True)   # MATH|ELA
    period: Mapped[str] = mapped_column(String, index=True)    # PM1|PM2|PM3
    category: Mapped[str] = mapped_column(String, default="")  # domain/reporting category
    benchmark_code: Mapped[str] = mapped_column(String, index=True)  # MA.3.FR.1.3
    points_earned: Mapped[float] = mapped_column(Float, default=0)
    points_possible: Mapped[float] = mapped_column(Float, default=0)
    item_index: Mapped[int] = mapped_column(Integer, default=0)
    school_year: Mapped[str] = mapped_column(String, default="2025-2026")


class PlcAgenda(Base, TimestampMixin):
    """An auto-generated collaborative-planning (PLC) agenda for a pacing week."""
    __tablename__ = "plc_agendas"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    pacing_topic_id: Mapped[str] = mapped_column(
        ForeignKey("pacing_topics.id"), index=True
    )
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)


class CalendarEntry(Base, TimestampMixin):
    """A single day on a grade's pacing calendar: which lesson (or review /
    assessment) is scheduled for that date. Dates are stored as ISO strings
    (YYYY-MM-DD) for SQLite/Postgres portability."""
    __tablename__ = "calendar_entries"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    grade_level: Mapped[str] = mapped_column(String, index=True)
    subject: Mapped[str] = mapped_column(String, default="MATH")
    date: Mapped[str] = mapped_column(String, index=True)   # YYYY-MM-DD
    topic_code: Mapped[str] = mapped_column(String, default="")
    lesson_code: Mapped[str] = mapped_column(String, default="")
    title: Mapped[str] = mapped_column(String, default="")
    kind: Mapped[str] = mapped_column(String, default="lesson")  # lesson|review|assessment|note
    note: Mapped[str] = mapped_column(String, default="")


class SavedGuide(Base, TimestampMixin):
    """A generated Collaborative Planning Guide, persisted so it isn't lost when
    the coach navigates away. Reopenable and downloadable from the DB."""
    __tablename__ = "saved_guides"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    grade_level: Mapped[str] = mapped_column(String, default="", index=True)
    topic_code: Mapped[str] = mapped_column(String, default="", index=True)
    subject: Mapped[str] = mapped_column(String, default="MATH")
    title: Mapped[str] = mapped_column(String, default="")
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String, default="")
    # Generation runs in the background so the request returns immediately;
    # the page polls this guide until status is "ready" (or "error").
    status: Mapped[str] = mapped_column(String, default="ready")  # generating|ready|error
    error: Mapped[str] = mapped_column(Text, default="")


class PlanningDocument(Base, TimestampMixin):
    """A file the coach uploads into a grade/topic folder in the planning area
    (pacing guides, bell ringers, year-at-a-glance, resources...). Stored in the
    DB so it survives the ephemeral filesystem. topic_code is empty for
    grade-level documents (e.g. Year at a Glance)."""
    __tablename__ = "planning_documents"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    grade_level: Mapped[str] = mapped_column(String, index=True)
    topic_code: Mapped[str] = mapped_column(String, default="", index=True)
    subject: Mapped[str] = mapped_column(String, default="MATH")
    name: Mapped[str] = mapped_column(String)          # display name
    filename: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String, default="application/octet-stream")
    size: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    uploaded_by: Mapped[str] = mapped_column(String, default="")


class KeyDate(Base, TimestampMixin):
    """A district/school date the coach needs to stay ahead of: assessment
    windows, report-card/progress-report dates, planning days, faculty & EESAC
    meetings, drills. Single-day events set date only; windows set date +
    end_date. Seeded from the school calendar, and editable by the coach."""
    __tablename__ = "key_dates"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    title: Mapped[str] = mapped_column(String)
    # assessment | progress_report | report_card | planning_day |
    # vertical_planning | faculty_meeting | eesac_meeting | drill |
    # emergency_drill | custom
    category: Mapped[str] = mapped_column(String, default="custom", index=True)
    date: Mapped[str] = mapped_column(String, index=True)      # ISO yyyy-mm-dd
    end_date: Mapped[str] = mapped_column(String, default="")  # ISO, "" if single-day
    grade: Mapped[str] = mapped_column(String, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String, default="custom")
    created_by: Mapped[str] = mapped_column(String, default="")


class ScheduleBlock(Base, TimestampMixin):
    """A time block from the school master schedule, parsed per teacher/day.
    kind='math' = when the teacher teaches math (visit window); kind='di' =
    their Science/Social-Studies block, which is when they can run Math DI."""
    __tablename__ = "schedule_blocks"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    grade: Mapped[str] = mapped_column(String, default="", index=True)
    room: Mapped[str] = mapped_column(String, default="")
    teacher_name: Mapped[str] = mapped_column(String, default="", index=True)
    program: Mapped[str] = mapped_column(String, default="")  # "" | ASD
    day: Mapped[str] = mapped_column(String, default="")     # Mon..Fri
    kind: Mapped[str] = mapped_column(String, default="math", index=True)  # math|di
    subject: Mapped[str] = mapped_column(String, default="")
    start_time: Mapped[str] = mapped_column(String, default="")  # HH:MM
    end_time: Mapped[str] = mapped_column(String, default="")


class FrameworkApplication(Base, TimestampMixin):
    """A scripted application of one Framework component to a specific grade +
    topic (how the week's coaching lens plays out in that content)."""
    __tablename__ = "framework_applications"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    grade: Mapped[str] = mapped_column(String, default="", index=True)
    topic_code: Mapped[str] = mapped_column(String, default="", index=True)
    topic_name: Mapped[str] = mapped_column(String, default="")
    component_key: Mapped[str] = mapped_column(String, default="")
    component_name: Mapped[str] = mapped_column(String, default="")
    week_focus: Mapped[str] = mapped_column(String, default="")
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String, default="")


class AppSetting(Base, TimestampMixin):
    """Small per-tenant key/value settings (e.g. the A/B rotation anchor)."""
    __tablename__ = "app_settings"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    key: Mapped[str] = mapped_column(String, index=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class CollabMeeting(Base, TimestampMixin):
    """A math collaborative-planning (CPT) meeting in the A/B two-week rotation:
    when the coach meets a grade's math team. Host is this year's teacher."""
    __tablename__ = "collab_meetings"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    week: Mapped[str] = mapped_column(String, default="A")     # A | B
    day: Mapped[str] = mapped_column(String, default="")        # Mon..Fri
    time: Mapped[str] = mapped_column(String, default="")       # HH:MM
    grade: Mapped[str] = mapped_column(String, default="", index=True)
    group: Mapped[str] = mapped_column(String, default="")      # Gen Ed | ASD | ESOL | ...
    host: Mapped[str] = mapped_column(String, default="")       # this year's teacher
    note: Mapped[str] = mapped_column(Text, default="")


class CoachNote(Base, TimestampMixin):
    """A coach's note about a teacher — the on-ramp to coaching cycles. Captures
    focus areas, observations, and next steps tied to a teacher (the CRM
    "account"). kind lets the UI separate a running note from a focus area or a
    follow-up next step."""
    __tablename__ = "coach_notes"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String, default="note")  # note|focus|next_step
    body: Mapped[str] = mapped_column(Text, default="")
    # Optional due date for next_step items (ISO yyyy-mm-dd); "" if none.
    due_date: Mapped[str] = mapped_column(String, default="")
    done: Mapped[bool] = mapped_column(Boolean, default=False)
