"""Database tables. Monthly amounts are stored as twelve columns, m1 (April) to m12 (March)."""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

MONTH_COLS = [f"m{i}" for i in range(1, 13)]


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    perms: Mapped[dict] = mapped_column(JSON, default=dict)
    users: Mapped[list["User"]] = relationship(back_populates="role")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    scope: Mapped[str] = mapped_column(String(10), default="all")  # all | some
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    role: Mapped[Role] = relationship(back_populates="users", lazy="joined")
    heads: Mapped[list["UserHead"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class UserHead(Base):
    """Heads a user may change when their scope is 'some'. Matched by head code, which stays the same across years."""
    __tablename__ = "user_heads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    section: Mapped[str] = mapped_column(String(10))
    head_code: Mapped[str] = mapped_column(String(36))
    head_name: Mapped[str] = mapped_column(String(160))


class FiscalYear(Base):
    __tablename__ = "fiscal_years"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    start_year: Mapped[int] = mapped_column(Integer, unique=True)
    limit_rule: Mapped[str] = mapped_column(String(10), default="block")  # block | warn
    total_limit_mode: Mapped[str] = mapped_column(String(10), default="none")  # none | amount | growth
    total_limit_value: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    heads: Mapped[list["Head"]] = relationship(
        back_populates="year", cascade="all, delete-orphan", order_by="Head.sort_order"
    )

    transfers: Mapped[list["BudgetTransfer"]] = relationship(cascade="all, delete-orphan")

    @property
    def label(self) -> str:
        return f"{self.start_year}-{str(self.start_year + 1)[2:]}"


class Head(Base):
    __tablename__ = "heads"
    __table_args__ = (UniqueConstraint("year_id", "section", "code", name="uq_head_code"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    year_id: Mapped[int] = mapped_column(ForeignKey("fiscal_years.id", ondelete="CASCADE"), index=True)
    section: Mapped[str] = mapped_column(String(10))  # expense | income
    code: Mapped[str] = mapped_column(String(36))
    name: Mapped[str] = mapped_column(String(160))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    limit_mode: Mapped[str] = mapped_column(String(10), default="none")
    limit_value: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    year: Mapped[FiscalYear] = relationship(back_populates="heads")
    lines: Mapped[list["Line"]] = relationship(
        back_populates="head", cascade="all, delete-orphan", order_by="Line.sort_order", lazy="selectin"
    )


class Line(Base):
    __tablename__ = "lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    head_id: Mapped[int] = mapped_column(ForeignKey("heads.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(36))
    name: Mapped[str] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    qty: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    rate: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    spread: Mapped[str] = mapped_column(String(10), default="equal")
    once_month: Mapped[int] = mapped_column(Integer, default=0)
    m1: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    m2: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    m3: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    m4: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    m5: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    m6: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    m7: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    m8: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    m9: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    m10: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    m11: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    m12: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    head: Mapped[Head] = relationship(back_populates="lines")


class BudgetTransfer(Base):
    """Audit record for a budget transfer between two lines."""
    __tablename__ = "budget_transfers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    year_id: Mapped[int] = mapped_column(
        ForeignKey("fiscal_years.id", ondelete="CASCADE"), index=True
    )
    section: Mapped[str] = mapped_column(String(10))
    month: Mapped[int] = mapped_column(Integer)  # 0 = April, 11 = March
    from_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("lines.id", ondelete="SET NULL"), nullable=True
    )
    to_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("lines.id", ondelete="SET NULL"), nullable=True
    )
    from_head_code: Mapped[str] = mapped_column(String(36))
    from_head_name: Mapped[str] = mapped_column(String(160))
    from_line_name: Mapped[str] = mapped_column(String(200))
    to_head_code: Mapped[str] = mapped_column(String(36))
    to_head_name: Mapped[str] = mapped_column(String(160))
    to_line_name: Mapped[str] = mapped_column(String(200))
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    reason: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(10), default="done")
    reverses_id: Mapped[int | None] = mapped_column(
        ForeignKey("budget_transfers.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Activity(Base):
    __tablename__ = "activity_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    user_name: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(Text)
    group_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
