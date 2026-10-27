"""Budget planner API (FastAPI). Run: uvicorn app.main:app --reload"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import CORS_ORIGINS, Base, engine
from .routers import admin, auth, budget, plan_files, templates, transfers

@asynccontextmanager
async def lifespan(_app):
    # Creates any missing tables. database/schema.sql holds the same structure for DBAs.
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Budget planner API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health():
    return {"ok": True}


for r in (auth.router, admin.router, budget.router, plan_files.router, transfers.router, templates.router):
    app.include_router(r)
