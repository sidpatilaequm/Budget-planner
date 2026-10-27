"""Budget transfers: move budget from one line (activity) to another within the same month.

- Within a head: both lines are under the same head, so the head total does not change.
- From another head: the lines are under different heads; budget leaves one head and joins the other.

Rules, all enforced here:
- The user needs "Transfer budgets between lines" and must be allowed to change amounts in BOTH heads,
  so a user limited to some heads can move budget only among those heads.
- Both lines are in the same year and section, and the amount is positive and no more than the source
  line holds in that month (a line never goes negative).
- The total for the year does not change. Moving budget into a head that has a limit is checked
  against that limit, using the year's rule (block or warn).
- A transfer can be reversed once, provided the destination still holds the amount in that month.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import MONTH_COLS, BudgetTransfer, FiscalYear, Line, User
from ..security import can, can_edit_amounts, current_user, deny
from ..services import budget as B

router = APIRouter(prefix="/api", tags=["transfers"])
MONTH_NAMES = ["April", "May", "June", "July", "August", "September", "October", "November", "December",
               "January", "February", "March"]


class TransferIn(BaseModel):
    from_line_id: int
    to_line_id: int
    month: int
    amount: float
    reason: str


class ReverseIn(BaseModel):
    reason: str | None = None


def transfer_out(t: BudgetTransfer) -> dict:
    return {
        "id": t.id, "section": t.section, "month": t.month, "month_name": MONTH_NAMES[t.month],
        "from": {"line_id": t.from_line_id, "line": t.from_line_name, "head": t.from_head_name, "head_code": t.from_head_code},
        "to": {"line_id": t.to_line_id, "line": t.to_line_name, "head": t.to_head_name, "head_code": t.to_head_code},
        "kind": "within" if t.from_head_code == t.to_head_code else "cross",
        "amount": float(t.amount), "reason": t.reason, "status": t.status, "reverses_id": t.reverses_id,
        "created_by": t.created_by_name, "created_at": t.created_at.isoformat() + "Z",
    }


def _month_value(line: Line, month: int) -> float:
    return float(getattr(line, MONTH_COLS[month]) or 0)


def _move(db: Session, user: User, year: FiscalYear, src: Line, dst: Line, month: int, amount: float,
          reason: str, reverses: BudgetTransfer | None = None) -> tuple[BudgetTransfer, str | None]:
    if not can(user, "transfer_budget"):
        deny("Your role does not allow budget transfers.")
    if not 0 <= month <= 11:
        raise HTTPException(422, "Choose a month from April to March.")
    if src.id == dst.id:
        raise HTTPException(422, "Choose two different lines.")
    if src.head.year_id != year.id or dst.head.year_id != year.id:
        raise HTTPException(422, "Both lines must be in this financial year.")
    if src.head.section != dst.head.section:
        raise HTTPException(422, "Budget can only move between two expense lines or two income lines.")
    for h in (src.head, dst.head):
        if not can_edit_amounts(user, h):
            deny(f"You cannot change amounts in “{h.name}”, so you cannot move budget into or out of it.")
    amount = round(float(amount or 0), 2)
    if amount <= 0:
        raise HTTPException(422, "Enter an amount greater than zero.")
    available = _month_value(src, month)
    if amount > available + 0.005:
        raise HTTPException(422, f"“{src.name}” has only ₹{available:,.2f} in {MONTH_NAMES[month]}. "
                                 "Transfer that much or less.")
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise HTTPException(422, "Give a reason for the transfer.")

    before = B.snapshot_expense(year)
    col = MONTH_COLS[month]
    setattr(src, col, round(available - amount, 2))
    setattr(dst, col, round(_month_value(dst, month) + amount, 2))
    t = BudgetTransfer(
        year_id=year.id, section=src.head.section, month=month, from_line_id=src.id, to_line_id=dst.id,
        from_head_code=src.head.code, to_head_code=dst.head.code, from_head_name=src.head.name,
        to_head_name=dst.head.name, from_line_name=src.name, to_line_name=dst.name,
        amount=Decimal(str(amount)), reason=reason[:300], status="reversal" if reverses else "done",
        reverses_id=reverses.id if reverses else None, created_by_id=user.id, created_by_name=user.name)
    db.add(t)
    warning = B.enforce_limits(db, year, before) if src.head.section == "expense" else None
    return t, warning


@router.get("/years/{year_id}/transfers")
def list_transfers(year_id: int, section: str = "expense", db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    if section not in ("expense", "income"):
        raise HTTPException(404, "Unknown section.")
    if not can(user, f"view_{section}"):
        deny()
    y = B.get_year(db, year_id)
    rows = db.scalars(select(BudgetTransfer).where(BudgetTransfer.year_id == y.id, BudgetTransfer.section == section)
                      .order_by(BudgetTransfer.created_at.desc(), BudgetTransfer.id.desc())).all()
    # Net effect by head, counting reversals so a reversed transfer nets to nothing.
    heads: dict = {}
    for t in rows:
        if t.from_head_code == t.to_head_code:
            h = heads.setdefault(t.from_head_code, {"head": t.from_head_name, "in": 0.0, "out": 0.0, "within": 0.0})
            h["within"] += float(t.amount) if t.status != "reversal" else -float(t.amount)
            continue
        out_h = heads.setdefault(t.from_head_code, {"head": t.from_head_name, "in": 0.0, "out": 0.0, "within": 0.0})
        in_h = heads.setdefault(t.to_head_code, {"head": t.to_head_name, "in": 0.0, "out": 0.0, "within": 0.0})
        out_h["out"] += float(t.amount)
        in_h["in"] += float(t.amount)
    current = {h.code: h.name for h in B.section_heads(y, section)}
    summary = []
    for code, h in heads.items():
        net = round(h["in"] - h["out"], 2)
        summary.append({"head_code": code, "head": current.get(code, h["head"]), "in": round(h["in"], 2),
                        "out": round(h["out"], 2), "net": net, "within": round(h["within"], 2)})
    summary.sort(key=lambda r: r["head"].lower())
    return {"year": B.year_out(y), "section": section, "transfers": [transfer_out(t) for t in rows],
            "summary": summary}


@router.post("/years/{year_id}/transfers")
def create_transfer(year_id: int, body: TransferIn, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    y = B.get_year(db, year_id)
    src, dst = db.get(Line, body.from_line_id), db.get(Line, body.to_line_id)
    if not src or not dst:
        raise HTTPException(404, "One of those lines no longer exists. Reload the page.")
    t, warning = _move(db, user, y, src, dst, body.month, body.amount, body.reason)
    kind = "within “" + src.head.name + "”" if src.head_id == dst.head_id else f"from “{src.head.name}” to “{dst.head.name}”"
    B.log(db, user, f"Transferred ₹{float(t.amount):,.2f} in {MONTH_NAMES[t.month]} from “{src.name}” to “{dst.name}” "
                    f"({kind}), FY {y.label}: {t.reason}")
    db.commit()
    return {"transfer": transfer_out(t), "warning": warning,
            "lines": [B.line_out(src), B.line_out(dst)]}


@router.post("/transfers/{transfer_id}/reverse")
def reverse_transfer(transfer_id: int, body: ReverseIn, db: Session = Depends(get_db),
                     user: User = Depends(current_user)):
    t = db.get(BudgetTransfer, transfer_id)
    if not t:
        raise HTTPException(404, "That transfer does not exist. Reload the page.")
    if t.status != "done":
        raise HTTPException(409, "This transfer has already been reversed, or is itself a reversal.")
    src, dst = db.get(Line, t.to_line_id) if t.to_line_id else None, db.get(Line, t.from_line_id) if t.from_line_id else None
    if not src or not dst:
        raise HTTPException(409, "A line in this transfer has been deleted, so it cannot be reversed.")
    y = B.get_year(db, t.year_id)
    reason = (body.reason or "").strip() or f"Reversal of transfer #{t.id}"
    r, warning = _move(db, user, y, src, dst, t.month, float(t.amount), reason, reverses=t)
    t.status = "reversed"
    B.log(db, user, f"Reversed the transfer of ₹{float(t.amount):,.2f} in {MONTH_NAMES[t.month]} from “{t.from_line_name}” "
                    f"to “{t.to_line_name}” (FY {y.label})")
    db.commit()
    return {"transfer": transfer_out(r), "warning": warning}
