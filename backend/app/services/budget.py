"""Budget arithmetic, limit checks, year copying and the activity log."""
import uuid
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..catalog import EXPENSE_TEMPLATE, INCOME_TEMPLATE
from ..models import MONTH_COLS, Activity, FiscalYear, Head, Line, User, utcnow

INSTALLMENTS = [(0, 4), (4, 8), (8, 12)]  # Apr–Jul, Aug–Nov, Dec–Mar


def new_code() -> str:
    return uuid.uuid4().hex


def fnum(v) -> float | None:
    return None if v is None else float(v)


def months(line: Line) -> list[float]:
    return [float(getattr(line, c) or 0) for c in MONTH_COLS]


def set_months(line: Line, values: list[float]) -> None:
    if len(values) != 12:
        raise HTTPException(422, "Send exactly 12 monthly amounts, April to March.")
    for c, v in zip(MONTH_COLS, values):
        setattr(line, c, round(float(v or 0), 2))


def line_total(line: Line) -> float:
    return sum(months(line))


def head_total(head: Head) -> float:
    return sum(line_total(l) for l in head.lines)


def spread(total: float, pattern: str, once: int = 0, existing: list[float] | None = None) -> list[float]:
    """Split a yearly amount into 12 months (whole rupees); any rounding remainder goes to the last paying month."""
    if pattern == "inst3":
        w = [1 if k in (0, 4, 8) else 0 for k in range(12)]
    elif pattern == "quarterly":
        w = [1 if k in (0, 3, 6, 9) else 0 for k in range(12)]
    elif pattern == "once":
        w = [1 if k == int(once or 0) else 0 for k in range(12)]
    elif pattern == "keep":
        e = [float(v or 0) for v in (existing or [0] * 12)]
        w = e if sum(e) != 0 else [1] * 12
    else:
        w = [1] * 12
    ws = sum(w)
    t = round(total)
    out = [round(t * x / ws) for x in w]
    last = max(k for k in range(12) if w[k]) if any(w) else 11
    out[last] += t - sum(out)
    return [float(v) for v in out]


def section_heads(year: FiscalYear, section: str) -> list[Head]:
    return [h for h in year.heads if h.section == section]


def year_by_start(db: Session, start: int) -> FiscalYear | None:
    return db.scalar(select(FiscalYear).where(FiscalYear.start_year == start))


def get_year(db: Session, year_id: int) -> FiscalYear:
    y = db.get(FiscalYear, year_id)
    if not y:
        raise HTTPException(404, "That financial year does not exist.")
    return y


# ---------- limits ----------

def prev_expense_totals(db: Session, year: FiscalYear) -> tuple[dict, dict, float | None]:
    """Last year's expense totals by head code and by lower-case name, plus the overall total."""
    pv = year_by_start(db, year.start_year - 1)
    if not pv:
        return {}, {}, None
    by_code, by_name = {}, {}
    for h in section_heads(pv, "expense"):
        t = head_total(h)
        by_code[h.code] = t
        by_name[h.name.lower()] = t
    return by_code, by_name, sum(by_code.values())


def resolve_limit(mode: str | None, value, base: float | None) -> float | None:
    if not mode or mode == "none" or value is None:
        return None
    if mode == "amount":
        return float(value)
    if mode == "growth":
        return None if base is None else base * (1 + float(value) / 100)
    return None


def head_base(head: Head, prev) -> float | None:
    by_code, by_name, _ = prev
    if head.code in by_code:
        return by_code[head.code]
    return by_name.get(head.name.lower())


def head_limit(head: Head, prev) -> float | None:
    return resolve_limit(head.limit_mode, head.limit_value, head_base(head, prev))


def total_limit(year: FiscalYear, prev) -> float | None:
    return resolve_limit(year.total_limit_mode, year.total_limit_value, prev[2])


def has_limits(year: FiscalYear, prev) -> bool:
    return total_limit(year, prev) is not None or any(
        head_limit(h, prev) is not None for h in section_heads(year, "expense"))


def snapshot_expense(year: FiscalYear) -> dict:
    heads = section_heads(year, "expense")
    return {"heads": {h.id: head_total(h) for h in heads}, "total": sum(head_total(h) for h in heads)}


def check_limits(db: Session, year: FiscalYear, before: dict) -> str | None:
    """Call after changing expense amounts in memory. Returns a message when a head or the total went
    over its limit *and* grew; with the 'block' rule the caller must roll back."""
    prev = prev_expense_totals(db, year)
    heads = section_heads(year, "expense")
    for h in heads:
        lim = head_limit(h, prev)
        t = head_total(h)
        if lim is not None and t > lim + 0.5 and t > before["heads"].get(h.id, 0) + 0.001:
            return f"“{h.name}” would be ₹{t - lim:,.0f} over its limit of ₹{lim:,.0f}"
    tl = total_limit(year, prev)
    tot = sum(head_total(h) for h in heads)
    if tl is not None and tot > tl + 0.5 and tot > before["total"] + 0.001:
        return f"Total expenses would be ₹{tot - tl:,.0f} over the overall limit of ₹{tl:,.0f}"
    return None


def enforce_limits(db: Session, year: FiscalYear, before: dict) -> str | None:
    """Raises 409 for the 'block' rule, otherwise returns a warning (or None)."""
    msg = check_limits(db, year, before)
    if msg and (year.limit_rule or "block") == "block":
        db.rollback()
        raise HTTPException(409, msg + ". Reduce another line first.")
    return msg


# ---------- serialising ----------

def line_out(line: Line) -> dict:
    return {"id": line.id, "code": line.code, "name": line.name, "qty": fnum(line.qty), "rate": fnum(line.rate),
            "spread": line.spread, "once": line.once_month, "m": months(line)}


def year_out(y: FiscalYear) -> dict:
    return {"id": y.id, "start": y.start_year, "label": y.label}


# ---------- creating years ----------

def add_head(db: Session, year: FiscalYear, section: str, name: str, code: str | None = None, order: int = 0) -> Head:
    h = Head(year=year, section=section, code=code or new_code(), name=name, sort_order=order)
    db.add(h)
    return h


def add_line(db: Session, head: Head, name: str, code: str | None = None, order: int = 0) -> Line:
    ln = Line(head=head, code=code or new_code(), name=name, sort_order=order,
              spread="inst3" if head.section == "income" else "equal")
    set_months(ln, [0] * 12)
    db.add(ln)
    return ln


def fill_template(db: Session, year: FiscalYear) -> None:
    for section, tpl in (("expense", EXPENSE_TEMPLATE), ("income", INCOME_TEMPLATE)):
        for hi, (hname, items) in enumerate(tpl):
            h = add_head(db, year, section, hname, order=hi)
            for li, n in enumerate(items):
                add_line(db, h, n, order=li)


def copy_year(db: Session, src: FiscalYear, dst: FiscalYear, with_amounts: bool, factor_fn=None) -> None:
    """Copies heads and lines (keeping their codes) from src into dst."""
    for h in src.heads:
        nh = Head(year=dst, section=h.section, code=h.code, name=h.name, sort_order=h.sort_order)
        db.add(nh)
        for ln in h.lines:
            nl = Line(head=nh, code=ln.code, name=ln.name, sort_order=ln.sort_order, spread=ln.spread,
                      once_month=ln.once_month, qty=ln.qty if with_amounts else None,
                      rate=ln.rate if with_amounts else None)
            set_months(nl, months(ln) if with_amounts else [0] * 12)
            db.add(nl)


# ---------- activity log ----------

def log(db: Session, user: User | None, action: str, key: str | None = None) -> None:
    """Adds an entry. Repeated edits with the same key by the same user within 10 minutes update one entry."""
    now = utcnow()
    if key and user:
        last = db.scalar(select(Activity).order_by(Activity.id.desc()).limit(1))
        if last and last.group_key == key and last.user_id == user.id and now - last.ts < timedelta(minutes=10):
            last.ts = now
            last.action = action
            return
    db.add(Activity(ts=now, user_id=user.id if user else None, user_name=user.name if user else "System",
                    action=action, group_key=key))
