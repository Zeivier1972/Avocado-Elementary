"""Avocado API entrypoint."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.core.config import settings
from app.db.session import Base, engine
from app.routers import (
    assessments,
    auth,
    dashboard,
    di,
    health,
    standards,
    students,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # MVP: create tables on startup. Production migrates via Alembic (roadmap P1).
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Avocado API",
    version=__version__,
    description="Instructional intelligence platform for M-DCPS.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (health, auth, standards, students, dashboard, assessments, di):
    app.include_router(r.router)


@app.get("/")
def root():
    return {"name": "Avocado API", "version": __version__,
            "docs": "/docs", "health": "/health"}
