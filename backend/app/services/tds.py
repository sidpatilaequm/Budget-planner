"""TDS: which payments attract tax deducted at source, how much should have been deducted, and what is due.

Rules applied per payee and category for the financial year (thresholds and rates come from the TDS
categories table, which HR or finance can edit):
- Single and yearly limits (contractors): TDS applies to a payment above the single limit; once the
  year's total passes the yearly limit, it applies to the whole year's total, including earlier payments.
- Yearly limit only (professional fees, commission, interest, goods): once the total passes the limit,
  TDS applies to the whole total.
- Monthly limit (rent): TDS applies to each month whose rent passes the limit.
- Rate: a valid lower-deduction certificate's rate; else the higher no-PAN rate when the payee has no PAN;
  else the individual/HUF or other rate.
Deposits are due by the 7th of the next month (30 April for March). Quarterly statements are due
31 July, 31 October, 31 January and 31 May.
"""
from datetime import date as Date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..catalog import NO_PAN_RATE, TDS_DEFAULTS
from ..models import ActualEntry, FiscalYear, LedgerMap, LineTds, Party, TdsDeposit, TdsReturn, TdsSection
from . import budget as B

PAN_RE = r"^[A-Z]{5}[0-9]{4}[A-Z]$"
QUARTERS = [(0, 3, "Q1 (April–June)"), (3, 6, "Q2 (July–September)"), (6, 9, "Q3 (October–December)"), (9, 12, "Q4 (January–March)")]


def seed_sections(db: Session) -> None:
    if db.scalar(select(TdsSection).limit(1)):
        return
    for code, label, new_ref, old_ref, ri, ro, single, annual, monthly in TDS_DEFAULTS:
        db.add(TdsSection(code=code, label=label, new_ref=new_ref, old_ref=old_ref, rate_ind=ri, rate_other=ro,
                          single_limit=single, annual_limit=annual, monthly_limit=monthly, active=True))


def section_out(s: TdsSection) -> dict:
    f = lambda v: None if v is None else float(v)  # noqa: E731
    return {"id": s.id, "code": s.code, "label": s.label, "new_ref": s.new_ref, "old_ref": s.old_ref, "rate_ind": f(s.rate_ind),
            "rate_other": f(s.rate_other), "single_limit": f(s.single_limit), "annual_limit": f(s.annual_limit),
            "monthly_limit": f(s.monthly_limit), "active": s.active}


def party_out(p: Party) -> dict:
    return {"id": p.id, "name": p.name, "pan": p.pan, "kind": p.kind, "tds_code": p.tds_code,
            "lower_rate": None if p.lower_rate is None else float(p.lower_rate), "lower_cert": p.lower_cert, "lower_valid_to": p.lower_valid_to}


def deposit_due(fy_start: int, month: int) -> str:
    """Due date for tax deducted in a month: 7th of the next month; 30 April for March."""
    if month == 11:
        return f"{fy_start + 1}-04-30"
    y, m = (fy_start, month + 5) if month <= 7 else (fy_start + 1, month - 7)   # month index → next calendar month
    return f"{y}-{m:02d}-07"


def return_due(fy_start: int, q: int) -> str:
    return [f"{fy_start}-07-31", f"{fy_start}-10-31", f"{fy_start + 1}-01-31", f"{fy_start + 1}-05-31"][q]


def _rate(sec: TdsSection, party: Party | None, on: str) -> tuple[float, str]:
    if party and party.lower_rate is not None and (not party.lower_valid_to or party.lower_valid_to >= on):
        return float(party.lower_rate), "lower-deduction certificate"
    if not party or not party.pan:
        base = float(sec.rate_ind if party and party.kind == "individual" else sec.rate_other)
        return max(float(NO_PAN_RATE), base), "no PAN"
    return float(sec.rate_ind if party.kind == "individual" else sec.rate_other), ""


def code_for(e: ActualEntry, maps: dict, line_tds: dict, parties: dict) -> str | None:
    if e.tds_code:
        return e.tds_code
    m = maps.get((e.ledger_name or "").lower())
    if m and m.tds_code:
        return m.tds_code
    lt = line_tds.get((e.head_code, e.line_code))
    if lt:
        return lt
    p = parties.get((e.party or "").strip().lower())
    return p.tds_code if p else None


def report(db: Session, fy_start: int) -> dict:
    secs = {s.code: s for s in db.scalars(select(TdsSection))}
    parties = {p.name.strip().lower(): p for p in db.scalars(select(Party))}
    maps = {m.ledger_name.lower(): m for m in db.scalars(select(LedgerMap))}
    line_tds = {(x.head_code, x.line_code): x.tds_code for x in db.scalars(select(LineTds))}
    entries = db.scalars(select(ActualEntry).where(ActualEntry.fy_start == fy_start, ActualEntry.section == "expense").order_by(ActualEntry.date)).all()

    groups: dict = {}
    for e in entries:
        code = code_for(e, maps, line_tds, parties)
        if not code or code not in secs:
            continue
        key = ((e.party or "(no party)").strip(), code)
        groups.setdefault(key, []).append(e)

    rows = []
    for (party_name, code), es in groups.items():
        s = secs[code]
        p = parties.get(party_name.lower())
        gross = sum(float(e.amount) for e in es)
        deducted = sum(float(e.tds_amount or 0) for e in es)
        last = es[-1].date
        rate, why = _rate(s, p, last)
        single = float(s.single_limit) if s.single_limit is not None else None
        annual = float(s.annual_limit) if s.annual_limit is not None else None
        monthly = float(s.monthly_limit) if s.monthly_limit is not None else None
        if monthly is not None:
            by_m = {}
            for e in es:
                by_m[e.month] = by_m.get(e.month, 0.0) + float(e.amount)
            taxable = sum(v for v in by_m.values() if v > monthly)
            near = max(by_m.values(), default=0) >= 0.8 * monthly and not taxable
            limit_text = f"₹{monthly:,.0f} a month"
        elif annual is not None and gross > annual:
            taxable, near = gross, False
            limit_text = f"₹{annual:,.0f} a year" + (f", ₹{single:,.0f} a payment" if single else "")
        else:
            taxable = sum(float(e.amount) for e in es if single is not None and float(e.amount) > single)
            near = annual is not None and gross >= 0.8 * annual and not taxable
            limit_text = (f"₹{annual:,.0f} a year" if annual is not None else "none") + (f", ₹{single:,.0f} a payment" if single else "")
        expected = round(taxable * rate / 100)
        short = round(expected - deducted)
        status = "not yet" if not taxable else "short" if short > 1 else "excess" if short < -1 else "ok"
        if near:
            status = "near"
        rows.append({"party": party_name, "party_id": p.id if p else None, "pan": p.pan if p else "", "kind": p.kind if p else "",
                     "code": code, "label": s.label, "new_ref": s.new_ref, "old_ref": s.old_ref, "payments": len(es),
                     "gross": round(gross, 2), "limit": limit_text, "taxable": round(taxable, 2), "rate": rate, "rate_note": why,
                     "expected": expected, "deducted": round(deducted, 2), "short": short, "status": status,
                     "remaining": (round(annual - gross, 2) if annual is not None and not taxable else None)})
    rows.sort(key=lambda r: ({"short": 0, "near": 1, "excess": 2, "ok": 3, "not yet": 4}[r["status"]], -r["gross"]))

    deducted_m = [0.0] * 12
    for e in entries:
        deducted_m[e.month] += float(e.tds_amount or 0)
    deps = db.scalars(select(TdsDeposit).where(TdsDeposit.fy_start == fy_start)).all()
    paid_m = [0.0] * 12
    for d in deps:
        paid_m[d.month] += float(d.amount)
    today = Date.today().isoformat()
    months = []
    for m in range(12):
        due = deposit_due(fy_start, m)
        pending = round(deducted_m[m] - paid_m[m], 2)
        st = "nothing" if not deducted_m[m] and not paid_m[m] else "paid" if pending <= 0.5 else "overdue" if today > due else "due"
        months.append({"month": m, "deducted": round(deducted_m[m], 2), "paid": round(paid_m[m], 2), "pending": pending, "due": due, "status": st})
    filed = {r.quarter: r for r in db.scalars(select(TdsReturn).where(TdsReturn.fy_start == fy_start))}
    quarters = []
    for q, (a, b, label) in enumerate(QUARTERS):
        due = return_due(fy_start, q)
        has = any(deducted_m[m] for m in range(a, b))
        r = filed.get(q + 1)
        quarters.append({"quarter": q + 1, "label": label, "due": due, "deducted": round(sum(deducted_m[a:b]), 2),
                         "filed_on": r.filed_on if r else None, "ack": r.ack if r else "",
                         "status": "filed" if r else "nothing" if not has else "overdue" if today > due else "due"})
    return {"fy": fy_start, "rows": rows, "months": months, "quarters": quarters,
            "deposits": [{"id": d.id, "month": d.month, "amount": float(d.amount), "paid_on": d.paid_on, "challan": d.challan} for d in deps],
            "totals": {"gross": round(sum(r["gross"] for r in rows), 2), "expected": sum(r["expected"] for r in rows),
                       "deducted": round(sum(deducted_m), 2), "short": sum(max(0, r["short"]) for r in rows),
                       "paid": round(sum(paid_m), 2)}}


def budgeted(db: Session, year: FiscalYear) -> dict:
    """TDS the budget implies: each budgeted expense line with a TDS category × the 'other payee' rate.
    An estimate for cash planning; actual deductions depend on the payee and the thresholds."""
    secs = {s.code: s for s in db.scalars(select(TdsSection))}
    line_tds = {(x.head_code, x.line_code): x.tds_code for x in db.scalars(select(LineTds))}
    lines, months = [], [0.0] * 12
    for h in B.section_heads(year, "expense"):
        for ln in h.lines:
            code = line_tds.get((h.code, ln.code))
            if not code or code not in secs:
                continue
            rate = float(secs[code].rate_other)
            m = [v * rate / 100 for v in B.months(ln)]
            months = [a + b for a, b in zip(months, m)]
            lines.append({"head": h.name, "line": ln.name, "code": code, "rate": rate, "budget": B.line_total(ln), "tds": round(sum(m))})
    return {"lines": lines, "months": [round(v) for v in months], "total": round(sum(months)),
            "due": [deposit_due(year.start_year, m) for m in range(12)]}


def lower_cert_expiring(db: Session, days: int = 30) -> list[Party]:
    soon = (Date.today() + timedelta(days=days)).isoformat()
    today = Date.today().isoformat()
    return [p for p in db.scalars(select(Party)) if p.lower_rate is not None and p.lower_valid_to and today <= p.lower_valid_to <= soon]
