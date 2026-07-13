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
