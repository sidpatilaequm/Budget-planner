"""Budget planner API (FastAPI). Run: uvicorn app.main:app --reload"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .catalog import NEW_PERM_DEFAULTS, V2_PERMS
from .db import CORS_ORIGINS, Base, SessionLocal, engine
from .models import Role
from .routers import actuals, admin, auth, budget, insights, plan_files, tally, tds, templates, transfers
from .services import tds as tds_service


def upgrade(db) -> None:
    """Version 2 start-up: TDS categories, and the new permissions for existing roles.
    A role gets a default for a new permission only if it has no value for it yet, so choices made
    later in Users and roles are never overwritten."""
    tds_service.seed_sections(db)
    for role in db.scalars(select(Role)):
        perms = dict(role.perms or {})
        missing = [k for k in V2_PERMS if k not in perms]
        if missing:
            on = set(NEW_PERM_DEFAULTS.get(role.name, []))
            for k in missing:
                perms[k] = k in on
            role.perms = perms
    db.commit()


@asynccontextmanager
async def lifespan(_app):
    # Creates any missing tables. database/schema.sql holds the same structure for DBAs.
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        upgrade(db)
    yield


app = FastAPI(title="Budget planner API", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health():
    return {"ok": True}


for r in (auth.router, admin.router, budget.router, plan_files.router, transfers.router, templates.router,
          actuals.router, tally.router, tds.router, insights.router):
    app.include_router(r)
