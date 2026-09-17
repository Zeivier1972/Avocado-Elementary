"""Health and readiness endpoints (used by Railway health checks)."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __build__, __version__
from app.core.config import settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok", "version": __version__, "build": __build__,
            "environment": settings.environment}


@router.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable"}
