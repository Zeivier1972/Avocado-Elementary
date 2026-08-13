"""Lightweight additive migrations run at startup.

The MVP uses Base.metadata.create_all, which creates missing *tables* but never
adds new *columns* to a table that already exists. Until we adopt Alembic
(roadmap Phase 1), this ensures newly-added columns exist on already-deployed
databases. Additive and idempotent — safe to run on every boot.
"""
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# table -> {column: SQL type} added after the initial release.
_ADDED_COLUMNS = {
    "pacing_topics": {
        "time_frame": "VARCHAR",
        "topic_focus": "TEXT",
        "ald_focus": "VARCHAR",
        "mtr_practices": "JSON",
        "materials": "JSON",
        "lessons": "JSON",
    },
    "saved_guides": {
        # Background generation status; existing rows are already-finished guides.
        "status": "VARCHAR DEFAULT 'ready'",
        "error": "TEXT DEFAULT ''",
    },
    "schedule_blocks": {
        "program": "VARCHAR DEFAULT ''",  # "" | ASD
    },
}
# student_assessments is a new table (create_all builds it) — no ALTERs needed.


def ensure_columns(engine: Engine) -> None:
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table, cols in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                continue  # create_all will build it fresh with all columns
            have = {c["name"] for c in insp.get_columns(table)}
            for name, sqltype in cols.items():
                if name in have:
                    continue
                # Postgres and SQLite both accept ADD COLUMN; keep it simple.
                conn.execute(
                    text(f'ALTER TABLE {table} ADD COLUMN {name} {sqltype}')
                )
