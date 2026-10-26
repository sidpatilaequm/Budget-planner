from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import FiscalYear, Head, Line, User
from ..security import (can, can_edit_amounts, can_edit_lines, can_manage_heads, current_user, deny,
                        require)
from ..services import budget as B

router = APIRouter(prefix="/api", tags=["budget"])
SECTIONS = ("expense", "income")


def found(obj, what: str):
    if not obj:
        raise HTTPException(404, f"That {what} does not exist. Reload the page.")
    return obj


def check_section(section: str):
    if section not in SECTIONS:
        raise HTTPException(404, "Unknown section.")


# ---------- years ----------

class YearIn(BaseModel):
    start: int
    source: str = "lines"          # lines | full | template
    from_year_id: int | None = None
    replace: bool = False


@router.get("/years")
def list_years(db: Session = Depends(get_db), user: User = Depends(current_user)):
    out = []
    for y in db.scalars(select(FiscalYear).order_by(FiscalYear.start_year)):
        row = B.year_out(y)
        if can(user, "view_expense"):
            row["expense"] = sum(B.head_total(h) for h in B.section_heads(y, "expense"))
        if can(user, "view_income"):
            row["income"] = sum(B.head_total(h) for h in B.section_heads(y, "income"))
        out.append(row)
    return out


@router.post("/years")
def create_year(body: YearIn, db: Session = Depends(get_db), user: User = Depends(require("manage_years"))):
    if not 1990 < body.start < 2200:
        raise HTTPException(422, "Enter a year such as 2027.")
    existing = B.year_by_start(db, body.start)
    if existing and not body.replace:
        raise HTTPException(409, f"FY {body.start}-{str(body.start + 1)[2:]} already exists.")
    src = B.get_year(db, body.from_year_id) if body.source != "template" else None
    if src and src.id == (existing.id if existing else None):
        raise HTTPException(422, "Choose a different year to copy from.")
    if existing:
        db.delete(existing)
        db.flush()
    y = FiscalYear(start_year=body.start)
    db.add(y)
    if src:
        B.copy_year(db, src, y, with_amounts=body.source == "full")
    else:
        B.fill_template(db, y)
    db.flush()
    B.log(db, user, f"Added FY {y.label}")
    db.commit()
    return B.year_out(y)


@router.delete("/years/{year_id}")
def delete_year(year_id: int, db: Session = Depends(get_db), user: User = Depends(require("manage_years"))):
    y = B.get_year(db, year_id)
    if db.query(FiscalYear).count() <= 1:
        raise HTTPException(409, "Keep at least one financial year.")
    B.log(db, user, f"Deleted FY {y.label}")
    db.delete(y)
    db.commit()
    return {"ok": True}


# ---------- budget sheets ----------

@router.get("/years/{year_id}/sections/{section}")
def get_section(year_id: int, section: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    check_section(section)
    if not can(user, f"view_{section}"):
        deny()
    y = B.get_year(db, year_id)
    prev = B.prev_expense_totals(db, y) if section == "expense" else ({}, {}, None)
    heads = []
    for h in B.section_heads(y, section):
        row = {"id": h.id, "code": h.code, "name": h.name, "can_edit": can_edit_amounts(user, h),
               "can_lines": can_edit_lines(user, h), "lines": [B.line_out(l) for l in h.lines]}
        if section == "expense":
            row["limit"] = B.head_limit(h, prev)
        heads.append(row)
    out = {"year": B.year_out(y), "section": section, "heads": heads, "can_manage_heads": can_manage_heads(user)}
    if section == "expense":
        out["total_limit"] = B.total_limit(y, prev)
        out["rule"] = y.limit_rule
    return out


class NameIn(BaseModel):
    name: str


@router.post("/years/{year_id}/sections/{section}/heads")
def add_head(year_id: int, section: str, body: NameIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    check_section(section)
    if not can_manage_heads(user):
        deny()
    y = B.get_year(db, year_id)
    order = max([h.sort_order for h in B.section_heads(y, section)] or [-1]) + 1
    h = B.add_head(db, y, section, body.name.strip() or "New head", order=order)
    B.add_line(db, h, "New line")
    db.flush()
    B.log(db, user, f"Added {section} head “{h.name}” in FY {y.label}")
    db.commit()
    return {"id": h.id}


@router.patch("/heads/{head_id}")
def rename_head(head_id: int, body: NameIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    h = found(db.get(Head, head_id), "head")
    if not can_manage_heads(user):
        deny()
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Enter a head name.")
    B.log(db, user, f"Renamed head “{h.name}” to “{name}” (FY {h.year.label})", key=f"hn:{h.id}")
    h.name = name
    db.commit()
    return {"ok": True}


@router.delete("/heads/{head_id}")
def delete_head(head_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    h = found(db.get(Head, head_id), "head")
    if not can_manage_heads(user):
        deny()
    B.log(db, user, f"Deleted head “{h.name}” (FY {h.year.label})")
    db.delete(h)
    db.commit()
    return {"ok": True}


@router.post("/heads/{head_id}/lines")
def add_line(head_id: int, body: NameIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    h = found(db.get(Head, head_id), "head")
    if not can_edit_lines(user, h):
        deny()
    order = max([l.sort_order for l in h.lines] or [-1]) + 1
    ln = B.add_line(db, h, body.name.strip() or "New line", order=order)
    db.flush()
    B.log(db, user, f"Added line “{ln.name}” to “{h.name}” (FY {h.year.label})")
    db.commit()
    return B.line_out(ln)


class LineIn(BaseModel):
    name: str | None = None
    m: list[float] | None = None
    qty: float | None = None
    rate: float | None = None
    set_qty_rate: bool = False      # true when qty/rate are being set (they may be null to clear them)
    spread: str | None = None
    once: int | None = None


@router.patch("/lines/{line_id}")
def update_line(line_id: int, body: LineIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ln = found(db.get(Line, line_id), "line")
    h, y = ln.head, ln.head.year
    amounts = body.m is not None or body.set_qty_rate or body.spread is not None or body.once is not None
    if body.name is not None and not can_edit_lines(user, h):
        deny()
    if amounts and not can_edit_amounts(user, h):
        deny()
    before = B.snapshot_expense(y)
    if body.name is not None:
        ln.name = body.name.strip() or ln.name
        B.log(db, user, f"Renamed a line in “{h.name}” to “{ln.name}” (FY {y.label})", key=f"ln:{ln.id}")
    if body.set_qty_rate:
        ln.qty, ln.rate = body.qty, body.rate
    if body.spread in ("equal", "inst3", "quarterly", "once"):
        ln.spread = body.spread
    if body.once is not None:
        ln.once_month = max(0, min(11, body.once))
    if body.m is not None:
        B.set_months(ln, body.m)
    elif body.set_qty_rate and ln.qty is not None and ln.rate is not None:
        B.set_months(ln, B.spread(float(ln.qty) * float(ln.rate), ln.spread, ln.once_month, B.months(ln)))
    warning = None
    if amounts:
        warning = B.enforce_limits(db, y, before) if h.section == "expense" else None
        B.log(db, user, f"Changed amounts for “{ln.name}” in “{h.name}” (FY {y.label})", key=f"amt:{ln.id}")
    db.commit()
    return {"line": B.line_out(ln), "warning": warning}


class BulkItem(BaseModel):
    id: int
    m: list[float]


class BulkIn(BaseModel):
    lines: list[BulkItem]


@router.post("/years/{year_id}/lines/bulk")
def bulk_update(year_id: int, body: BulkIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Used for pasting several rows from Excel. All rows are saved, or none."""
    y = B.get_year(db, year_id)
    before = B.snapshot_expense(y)
    lines = []
    for item in body.lines:
        ln = db.get(Line, item.id)
        if not ln or ln.head.year_id != y.id:
            raise HTTPException(404, "A pasted line no longer exists. Reload and try again.")
        if not can_edit_amounts(user, ln.head):
            deny("You cannot change one of the pasted lines.")
        B.set_months(ln, item.m)
        lines.append(ln)
    warning = B.enforce_limits(db, y, before)
    for ln in lines:
        B.log(db, user, f"Changed amounts for “{ln.name}” in “{ln.head.name}” (FY {y.label})", key=f"amt:{ln.id}")
    db.commit()
    return {"lines": [B.line_out(l) for l in lines], "warning": warning}


@router.delete("/lines/{line_id}")
def delete_line(line_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ln = found(db.get(Line, line_id), "line")
    if not can_edit_lines(user, ln.head):
        deny()
    B.log(db, user, f"Deleted line “{ln.name}” from “{ln.head.name}” (FY {ln.head.year.label})")
    db.delete(ln)
    db.commit()
    return {"ok": True}


# ---------- summary ----------

@router.get("/years/{year_id}/summary")
def summary(year_id: int, db: Session = Depends(get_db), user: User = Depends(require("view_summary", "view_expense", "view_income"))):
    y = B.get_year(db, year_id)
    pv = B.year_by_start(db, y.start_year - 1)
    out = {"year": B.year_out(y), "prev": B.year_out(pv) if pv else None}
    for section in SECTIONS:
        m = [0.0] * 12
        heads = []
        prev_by_code = {h.code: B.head_total(h) for h in B.section_heads(pv, section)} if pv else {}
        for h in B.section_heads(y, section):
            for ln in h.lines:
                m = [a + b for a, b in zip(m, B.months(ln))]
            heads.append({"name": h.name, "total": B.head_total(h), "prev": prev_by_code.get(h.code)})
        out[section] = {"months": m, "total": sum(m), "heads": heads,
                        "prev_total": sum(prev_by_code.values()) if pv else None}
    return out


# ---------- limits ----------

class LimitIn(BaseModel):
    mode: str
    value: float | None = None


class LimitsIn(BaseModel):
    rule: str | None = None
    total: LimitIn | None = None
    heads: dict[str, LimitIn] | None = None   # head id -> limit


def limits_out(db: Session, y: FiscalYear) -> dict:
    prev = B.prev_expense_totals(db, y)
    pv = B.year_by_start(db, y.start_year - 1)
    heads = []
    for h in B.section_heads(y, "expense"):
        heads.append({"id": h.id, "name": h.name, "mode": h.limit_mode or "none", "value": B.fnum(h.limit_value),
                      "base": B.head_base(h, prev), "limit": B.head_limit(h, prev), "budgeted": B.head_total(h)})
    return {"year": B.year_out(y), "prev": B.year_out(pv) if pv else None, "rule": y.limit_rule,
            "total": {"mode": y.total_limit_mode or "none", "value": B.fnum(y.total_limit_value),
                      "base": prev[2], "limit": B.total_limit(y, prev),
                      "budgeted": sum(x["budgeted"] for x in heads)},
            "heads": heads}


@router.get("/years/{year_id}/limits")
def get_limits(year_id: int, db: Session = Depends(get_db), _=Depends(require("manage_limits"))):
    return limits_out(db, B.get_year(db, year_id))


def _limit_ok(l: LimitIn, has_prev: bool):
    if l.mode not in ("none", "amount", "growth"):
        raise HTTPException(422, "Unknown limit type.")
    if l.mode == "growth" and not has_prev:
        raise HTTPException(422, "Growth limits need the previous year in the planner.")


@router.put("/years/{year_id}/limits")
def put_limits(year_id: int, body: LimitsIn, db: Session = Depends(get_db), user: User = Depends(require("manage_limits"))):
    y = B.get_year(db, year_id)
    has_prev = B.year_by_start(db, y.start_year - 1) is not None
    if body.rule in ("block", "warn"):
        y.limit_rule = body.rule
        B.log(db, user, f"Set limits to {'block' if body.rule == 'block' else 'warn on'} overages (FY {y.label})")
    if body.total:
        _limit_ok(body.total, has_prev)
        y.total_limit_mode = body.total.mode
        y.total_limit_value = body.total.value if body.total.mode != "none" else None
        B.log(db, user, f"Changed the overall expense limit (FY {y.label})", key=f"limt:{y.id}")
    if body.heads:
        by_id = {str(h.id): h for h in B.section_heads(y, "expense")}
        for hid, l in body.heads.items():
            h = by_id.get(hid)
            if not h:
                continue
            _limit_ok(l, has_prev)
            h.limit_mode = l.mode
            h.limit_value = l.value if l.mode != "none" else None
        names = ", ".join(f"“{by_id[k].name}”" for k in body.heads if k in by_id)
        B.log(db, user, f"Changed head limits for {names} (FY {y.label})" if len(body.heads) <= 3
              else f"Changed {len(body.heads)} head limits (FY {y.label})", key=f"limh:{y.id}:{','.join(sorted(body.heads))}")
    db.commit()
    return limits_out(db, y)
