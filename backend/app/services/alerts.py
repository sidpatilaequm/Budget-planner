"""Alerts, worked out each time they are asked for, so they always match the data.

TDS (needs "View the TDS report"):
- TDS short-deducted for a payee, or the payee has no PAN (higher rate applies)
- a payee near the yearly threshold: the next payment will attract TDS
- tax deducted in a month not yet deposited: due within 7 days, or overdue
- a quarterly TDS statement due within 15 days, or overdue
- a lower-deduction certificate expiring within 30 days
Budget (needs "View actuals"):
- an expense head spent more than its budget so far this year (by over 10%), or more than its full-year budget
- income collected more than 15% behind the budget so far
Tally (needs "Set up Tally"):
- ledgers from Tally not mapped to a budget line yet
- no Tally data received for 3 days once a connection is set up

Each alert has a key that includes what it is about and the amounts, so a dismissed alert comes back
when the situation changes.
"""
from datetime import date as Date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ActualEntry, AlertDismissal, FiscalYear, Setting, User
from ..security import can
from . import actuals as A
from . import budget as B
from . import tds as T

MONTHS = ["April", "May", "June", "July", "August", "September", "October", "November", "December", "January", "February", "March"]
inr = lambda v: "₹" + f"{round(v):,}"  # noqa: E731


def current_fy() -> int:
    d = Date.today()
    return d.year if d.month >= 4 else d.year - 1


def build(db: Session, user: User, fy_start: int | None = None) -> list[dict]:
    fy = fy_start or current_fy()
    out: list[dict] = []
    today = Date.today()
    if can(user, "view_tds"):
        rep = T.report(db, fy)
        for r in rep["rows"]:
            ref = f"{r['new_ref']} (old {r['old_ref']})"
            if r["status"] == "short":
                out.append({"key": f"tds-short:{r['party']}:{r['code']}:{r['short']}", "severity": "high", "area": "TDS", "tab": "tds",
                            "title": f"TDS short by {inr(r['short'])}: {r['party']}",
                            "detail": f"{r['label']}, {ref}. Paid {inr(r['gross'])} this year; {inr(r['expected'])} should have been deducted at {r['rate']:g}%{' (' + r['rate_note'] + ')' if r['rate_note'] else ''}, {inr(r['deducted'])} was."})
            if r["status"] in ("short", "ok", "excess") and not r["pan"]:
                out.append({"key": f"tds-pan:{r['party']}", "severity": "high", "area": "TDS", "tab": "tds",
                            "title": f"No PAN for {r['party']}",
                            "detail": f"Payments attract TDS under {ref}. Without a PAN the rate is at least 20%. Add the PAN under TDS → Payees."})
            if r["status"] == "near":
                out.append({"key": f"tds-near:{r['party']}:{r['code']}:{round(r['gross'])}", "severity": "medium", "area": "TDS", "tab": "tds",
                            "title": f"{r['party']} is close to the TDS threshold",
                            "detail": f"{inr(r['gross'])} paid this year against the {r['limit']} limit for {r['label'].lower()}. "
                                      f"Deduct TDS from the payment that crosses it, on the whole year's amount."})
        for m in rep["months"]:
            if m["status"] in ("due", "overdue"):
                due = Date.fromisoformat(m["due"])
                if m["status"] == "overdue" or due - today <= timedelta(days=7):
                    out.append({"key": f"tds-dep:{fy}:{m['month']}:{m['pending']}", "severity": "high" if m["status"] == "overdue" else "medium",
                                "area": "TDS", "tab": "tds",
                                "title": f"TDS for {MONTHS[m['month']]} {'overdue' if m['status'] == 'overdue' else 'due'}: {inr(m['pending'])}",
                                "detail": f"Deposit by {due.strftime('%d %b %Y')}. Interest applies for late payment. Record the challan under TDS → Deposits."})
        for q in rep["quarters"]:
            if q["status"] in ("due", "overdue"):
                due = Date.fromisoformat(q["due"])
                if q["status"] == "overdue" or due - today <= timedelta(days=15):
                    out.append({"key": f"tds-ret:{fy}:{q['quarter']}", "severity": "high" if q["status"] == "overdue" else "medium",
                                "area": "TDS", "tab": "tds",
                                "title": f"Quarterly TDS statement {q['label']} {'overdue' if q['status'] == 'overdue' else 'due'}",
                                "detail": f"Due {due.strftime('%d %b %Y')}. Late filing attracts a fee for each day. Mark it filed under TDS → Returns."})
        for p in T.lower_cert_expiring(db):
            out.append({"key": f"tds-cert:{p.id}:{p.lower_valid_to}", "severity": "low", "area": "TDS", "tab": "tds",
                        "title": f"Lower-deduction certificate for {p.name} ends {p.lower_valid_to}",
                        "detail": "After it ends, the normal rate applies. Ask the payee for a new certificate if they have one."})

    year = B.year_by_start(db, fy)
    if year and can(user, "view_actuals"):
        upto = A.last_actual_month(db, fy)
        if upto >= 0:
            cmp_exp = A.compare(db, year, "expense")
            for h in cmp_exp["heads"]:
                b_ytd, a_ytd = sum(h["budget"][:upto + 1]), sum(h["actual"][:upto + 1])
                b_year = sum(h["budget"])
                if b_year and sum(h["actual"]) > b_year:
                    out.append({"key": f"bud-year:{h['code']}:{round(sum(h['actual']))}", "severity": "high", "area": "Budget", "tab": "compare",
                                "title": f"{h['name']}: over the full-year budget",
                                "detail": f"Spent {inr(sum(h['actual']))} against {inr(b_year)} for the year."})
                elif b_ytd and a_ytd > b_ytd * 1.1:
                    out.append({"key": f"bud-ytd:{h['code']}:{upto}:{round(a_ytd)}", "severity": "medium", "area": "Budget", "tab": "compare",
                                "title": f"{h['name']}: {round((a_ytd / b_ytd - 1) * 100)}% over budget so far",
                                "detail": f"{inr(a_ytd)} spent to the end of {MONTHS[upto]} against {inr(b_ytd)} budgeted."})
            cmp_inc = A.compare(db, year, "income")
            b_ytd, a_ytd = sum(cmp_inc["budget"][:upto + 1]), sum(cmp_inc["actual"][:upto + 1])
            if b_ytd and a_ytd < b_ytd * 0.85:
                out.append({"key": f"inc-ytd:{upto}:{round(a_ytd)}", "severity": "medium", "area": "Budget", "tab": "compare",
                            "title": f"Income {round((1 - a_ytd / b_ytd) * 100)}% behind budget",
                            "detail": f"{inr(a_ytd)} received to the end of {MONTHS[upto]} against {inr(b_ytd)} budgeted. Check fee collection."})

    if can(user, "manage_integration"):
        n = db.scalar(select(func.count(func.distinct(ActualEntry.ledger_name))).where(ActualEntry.section == "unmapped")) or 0
        if n:
            out.append({"key": f"tally-unmapped:{n}", "severity": "medium", "area": "Tally", "tab": "actuals",
                        "title": f"{n} Tally ledger{'s' if n > 1 else ''} to map",
                        "detail": "Entries on these ledgers are not counted until each is mapped to a budget line, or set to ignore. See Actuals → Tally."})
        st = db.get(Setting, "tally")
        last = (st.value or {}).get("last_sync") if st else None
        if st and (st.value or {}).get("key_hash") or (st and (st.value or {}).get("host")):
            if not last or datetime.fromisoformat(last.rstrip("Z")) < datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=3):
                out.append({"key": f"tally-stale:{(last or '')[:10]}", "severity": "low", "area": "Tally", "tab": "actuals",
                            "title": "No data from Tally for 3 days" if last else "Tally is set up but has not sent data yet",
                            "detail": "Check that the Tally bridge is running on the Tally computer, or run Sync now."})

    dismissed = {d.alert_key for d in db.scalars(select(AlertDismissal).where(AlertDismissal.user_id == user.id))}
    order = {"high": 0, "medium": 1, "low": 2}
    out = [a for a in out if a["key"] not in dismissed]
    out.sort(key=lambda a: order[a["severity"]])
    return out
