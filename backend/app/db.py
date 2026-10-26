"""Database engine, session factory and settings."""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL", "mysql+pymysql://budget:budget@localhost:3306/budget_planner?charset=utf8mb4"
)
JWT_SECRET = os.getenv("JWT_SECRET", "change-this-secret")
JWT_HOURS = int(os.getenv("JWT_HOURS", "8"))
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

_engine_args = {"pool_pre_ping": True, "future": True}
if DATABASE_URL.startswith("sqlite"):
    _engine_args["connect_args"] = {"check_same_thread": False}
else:
    _engine_args["pool_recycle"] = 1800

engine = create_engine(DATABASE_URL, **_engine_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
