"""Actual income and expenses: from Tally, from the entry screen or from an Excel import.

Entries are matched to budget lines by head and line code (stable across years), so the same mapping
works every year and actuals can be the base for next year's plan.
"""
from datetime import date as Date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import ActualEntry, FiscalYear, LedgerMap, User
from . import budget as B


def fy_of(iso: str) -> tuple[int, int]:
    """(financial year start, month index 0 = April) for a YYYY-MM-DD date."""
    try:
        d = Date.fromisoformat(iso[:10])
    except ValueError:
        raise HTTPException(422, "Enter the date as YYYY-MM-DD.")
    start = d.year if d.month >= 4 else d.year - 1
    return start, (d.month - 4) % 12


def entry_out(e: ActualEntry) -> dict:
    return {"id": e.id, "date": e.date, "fy": e.fy_start, "month": e.month, "section": e.section,
            "head_code": e.head_code, "line_code": e.line_code, "ledger": e.ledger_name, "party": e.party,
            "voucher_type": e.voucher_type, "voucher_no": e.voucher_no, "narration": e.narration,
            "amount": float(e.amount), "tds_code": e.tds_code, "tds_amount": float(e.tds_amount or 0),
            "source": e.source, "created_by": e.created_by_name}


def line_index(year: FiscalYear) -> dict:
    """(section, head_code, line_code) -> (head, line) for a year."""
    return {(h.section, h.code, ln.code): (h, ln) for h in year.heads for ln in h.lines}


def actual_months(db: Session, fy_start: int, section: str | None = None) -> dict:
    """(section, head_code, line_code) -> 12 monthly actual amounts."""
    q = select(ActualEntry).where(ActualEntry.fy_start == fy_start, ActualEntry.section.in_(("income", "expense")))
    if section:
        q = q.where(ActualEntry.section == section)
    out: dict = {}
    for e in db.scalars(q):
        k = (e.section, e.head_code, e.line_code)
        m = out.setdefault(k, [0.0] * 12)
        m[e.month] += float(e.amount)
    return out


def last_actual_month(db: Session, fy_start: int) -> int:
    """Index of the latest month that has any actual entry, or -1."""
    ms = [e.month for e in db.scalars(select(ActualEntry).where(ActualEntry.fy_start == fy_start, ActualEntry.section.in_(("income", "expense"))))]
    return max(ms) if ms else -1


def base_months(db: Session, year: FiscalYear, basis: str, upto: int | None = None) -> dict | None:
    """Monthly figures to plan from, per line id.
    budget   – the year's budget (None: the planning engine reads the lines itself)
    actual   – actual amounts for the year
    forecast – actuals up to and including month `upto` (default: the last month with actuals), budget after it
    """
    if basis not in ("actual", "forecast"):
        return None
    act = actual_months(db, year.start_year)
    if upto is None:
        upto = last_actual_month(db, year.start_year)
    out = {}
    for h in year.heads:
        for ln in h.lines:
            a = act.get((h.section, h.code, ln.code), [0.0] * 12)
            if basis == "actual":
                out[ln.id] = a
            else:
                b = B.months(ln)
                out[ln.id] = [a[i] if i <= upto else b[i] for i in range(12)]
    return out


def compare(db: Session, year: FiscalYear, section: str) -> dict:
    """Budget against actual for every head and line, month by month."""
    act = actual_months(db, year.start_year, section)
    upto = last_actual_month(db, year.start_year)
    heads = []
    known = set()
    for h in B.section_heads(year, section):
        lines = []
        for ln in h.lines:
            k = (section, h.code, ln.code)
            known.add(k)
            b, a = B.months(ln), act.get(k, [0.0] * 12)
            lines.append({"id": ln.id, "name": ln.name, "code": ln.code, "budget": b, "actual": a})
        hb = [sum(l["budget"][i] for l in lines) for i in range(12)]
        ha = [sum(l["actual"][i] for l in lines) for i in range(12)]
        heads.append({"id": h.id, "code": h.code, "name": h.name, "budget": hb, "actual": ha, "lines": lines})
    # actuals booked to lines that are not in this year's budget
    other = [{"head_code": k[1], "line_code": k[2], "actual": v} for k, v in act.items() if k not in known]
    tb = [sum(h["budget"][i] for h in heads) for i in range(12)]
    ta = [sum(h["actual"][i] for h in heads) + sum(o["actual"][i] for o in other) for i in range(12)]
    return {"year": B.year_out(year), "section": section, "upto": upto, "heads": heads, "other": other,
            "budget": tb, "actual": ta}


# ---------------------------------------------------------------- Tally vouchers
def ingest_vouchers(db: Session, vouchers: list[dict], date_from: str | None, date_to: str | None,
                    user: User | None, replace: bool = True) -> dict:
    """Saves Tally vouchers as actuals.

    Each voucher: {guid, date, type, number, party, narration, entries: [{ledger, amount}]}, where amount
    follows Tally's sign: negative = debit, positive = credit.
    - A ledger mapped to an expense line counts its debits; one mapped to an income line counts its credits.
    - A ledger mapped as TDS adds its credit to the tax deducted on that voucher's expenses.
    - Ledgers not mapped yet are kept so they can be mapped later; bank, cash and party ledgers are mapped
      to "ignore".
    With replace, Tally entries in the date range that are no longer in Tally are removed (deleted vouchers).
    """
    maps = {m.ledger_name.lower(): m for m in db.scalars(select(LedgerMap))}
    seen_guids, created, unmapped = set(), 0, set()
    for v in vouchers:
        guid = str(v.get("guid") or f"{v.get('type')}-{v.get('number')}-{v.get('date')}")
        seen_guids.add(guid)
        db.execute(delete(ActualEntry).where(ActualEntry.external_id.like(f"{guid}:%")))
        iso = _iso(v.get("date", ""))
        if not iso:
            continue
        fy, month = fy_of(iso)
        entries = v.get("entries") or []
        tds_total, tds_code = 0.0, None
        for en in entries:
            m = maps.get(str(en.get("ledger", "")).lower())
            if m and m.section == "tds":
                tds_total += float(en.get("amount") or 0)          # credit is positive
                tds_code = tds_code or m.tds_code
        rows = []
        for i, en in enumerate(entries):
            ledger = str(en.get("ledger", ""))
            amt = float(en.get("amount") or 0)
            m = maps.get(ledger.lower())
            if not m:
                unmapped.add(ledger)
                rows.append(ActualEntry(section="unmapped", amount=Decimal(str(round(abs(amt), 2)))))
            elif m.section in ("expense", "income"):
                value = -amt if m.section == "expense" else amt       # expense debit / income credit
                rows.append(ActualEntry(section=m.section, head_code=m.head_code, line_code=m.line_code,
                                        tds_code=m.tds_code, amount=Decimal(str(round(value, 2)))))
            else:
                rows.append(None)
                continue
            r = rows[-1]
            r.date, r.fy_start, r.month = iso, fy, month
            r.ledger_name, r.party = ledger[:200], str(v.get("party") or "")[:200]
            r.voucher_type, r.voucher_no = str(v.get("type") or "")[:60], str(v.get("number") or "")[:60]
            r.narration, r.source = str(v.get("narration") or "")[:500], "tally"
            r.external_id = f"{guid}:{i}"[:120]
            r.created_by_name = "Tally"
        # spread the voucher's TDS over its expense entries in proportion to their amounts
        exp = [r for r in rows if r is not None and r.section == "expense" and r.amount > 0]
        base = sum(float(r.amount) for r in exp)
        for r in exp:
            if tds_total and base:
                r.tds_amount = Decimal(str(round(tds_total * float(r.amount) / base, 2)))
                r.tds_code = r.tds_code or tds_code
        for r in rows:
            if r is not None:
                db.add(r)
                created += 1
    removed = 0
    if replace and date_from and date_to:
        stale = db.scalars(select(ActualEntry).where(ActualEntry.source == "tally", ActualEntry.date >= _iso(date_from),
                                                     ActualEntry.date <= _iso(date_to))).all()
        for e in stale:
            if (e.external_id or "").split(":")[0] not in seen_guids:
                db.delete(e)
                removed += 1
    if user is not None or vouchers:
        B.log(db, user, f"Tally sync: {len(vouchers)} vouchers, {created} entries"
                        f"{f', {removed} removed' if removed else ''}{f', {len(unmapped)} ledgers to map' if unmapped else ''}")
    return {"vouchers": len(vouchers), "entries": created, "removed": removed, "unmapped": sorted(unmapped)}


def remap_ledger(db: Session, m: LedgerMap) -> int:
    """Applies a (new or changed) ledger mapping to entries already received from Tally."""
    n = 0
    for e in db.scalars(select(ActualEntry).where(ActualEntry.source == "tally", ActualEntry.ledger_name == m.ledger_name)):
        n += 1
        if m.section in ("expense", "income"):
            if e.section == "unmapped":
                # unmapped entries keep the absolute amount; the voucher sign is needed to tell refunds apart,
                # so a re-sync from Tally is the exact path; until then treat it as a normal debit/credit
                pass
            e.section, e.head_code, e.line_code = m.section, m.head_code, m.line_code
            e.tds_code = e.tds_code or m.tds_code
        else:
            db.delete(e)
    return n


def _iso(s: str) -> str:
    """Tally dates are YYYYMMDD; the app uses YYYY-MM-DD."""
    s = str(s or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s[:10]
