"""TDS: categories and rates, payees, line categories, the report, budgeted TDS, deposits and returns."""
import csv
import io
import re
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import LineTds, Party, TdsDeposit, TdsReturn, TdsSection, User
from ..security import require
from ..services import actuals as A
from ..services import budget as B
from ..services import tds as T

router = APIRouter(prefix="/api/tds", tags=["tds"])
viewer = require("view_tds")
manager = require("manage_tds")
MONTHS = ["April", "May", "June", "July", "August", "September", "October", "November", "December", "January", "February", "March"]


class SectionIn(BaseModel):
    code: str
    label: str
    new_ref: str = ""
    old_ref: str = ""
    rate_ind: float
    rate_other: float
    single_limit: float | None = None
    annual_limit: float | None = None
    monthly_limit: float | None = None
    active: bool = True


class PartyIn(BaseModel):
    name: str
    pan: str = ""
    kind: str = "other"
    tds_code: str | None = None
    lower_rate: float | None = None
    lower_cert: str = ""
    lower_valid_to: str = ""


class LineTdsIn(BaseModel):
    head_code: str
    line_code: str
    tds_code: str | None = None


class DepositIn(BaseModel):
    fy: int
    month: int
    amount: float
    paid_on: str
    challan: str = ""


class ReturnIn(BaseModel):
    fy: int
    quarter: int
    filed_on: str
    ack: str = ""


# ---------------------------------------------------------------- categories
@router.get("/sections")
def sections(db: Session = Depends(get_db), _=Depends(viewer)):
    return [T.section_out(s) for s in db.scalars(select(TdsSection).order_by(TdsSection.id))]


@router.put("/sections")
def put_section(body: SectionIn, db: Session = Depends(get_db), user: User = Depends(manager)):
    code = re.sub(r"[^A-Z0-9_]", "", body.code.upper())[:20]
    if not code or not body.label.strip():
        raise HTTPException(422, "Enter a code and a description.")
    if not (0 <= body.rate_ind <= 100 and 0 <= body.rate_other <= 100):
        raise HTTPException(422, "Rates are percentages between 0 and 100.")
    s = db.scalar(select(TdsSection).where(TdsSection.code == code))
    if not s:
        s = TdsSection(code=code)
        db.add(s)
    for k in ("label", "new_ref", "old_ref", "rate_ind", "rate_other", "single_limit", "annual_limit", "monthly_limit", "active"):
        setattr(s, k, getattr(body, k))
    B.log(db, user, f"TDS category {code}: {body.rate_ind}% / {body.rate_other}%")
    db.commit()
    return T.section_out(s)


# ---------------------------------------------------------------- payees
@router.get("/parties")
def parties(db: Session = Depends(get_db), _=Depends(viewer)):
    return [T.party_out(p) for p in db.scalars(select(Party).order_by(Party.name))]


@router.put("/parties")
def put_party(body: PartyIn, db: Session = Depends(get_db), user: User = Depends(manager)):
    name = body.name.strip()
    pan = body.pan.strip().upper()
    if not name:
        raise HTTPException(422, "Enter the payee's name exactly as in the entries.")
    if pan and not re.match(T.PAN_RE, pan):
        raise HTTPException(422, "A PAN is 5 letters, 4 digits and a letter, e.g. ABCDE1234F.")
    if body.kind not in ("individual", "other"):
        raise HTTPException(422, "Choose individual/HUF or other.")
    p = db.scalar(select(Party).where(Party.name == name))
    if not p:
        p = Party(name=name)
        db.add(p)
    # the 4th letter of a PAN tells the holder type: P (individual) or H (HUF) are taxed as individuals
    p.pan, p.kind = pan, ("individual" if pan[3] in "PH" else "other") if pan else body.kind
    p.tds_code = body.tds_code or None
    p.lower_rate = body.lower_rate
    p.lower_cert, p.lower_valid_to = body.lower_cert.strip(), body.lower_valid_to.strip()
    B.log(db, user, f"TDS payee {name}{' PAN ' + pan if pan else ''}")
    db.commit()
    return T.party_out(p)


@router.delete("/parties/{party_id}")
def delete_party(party_id: int, db: Session = Depends(get_db), user: User = Depends(manager)):
    p = db.get(Party, party_id)
    if p:
        B.log(db, user, f"Removed TDS payee {p.name}")
        db.delete(p)
        db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- categories for budget lines
@router.get("/lines")
def line_codes(year_id: int, db: Session = Depends(get_db), _=Depends(viewer)):
    y = B.get_year(db, year_id)
    m = {(x.head_code, x.line_code): x.tds_code for x in db.scalars(select(LineTds))}
    return [{"head_code": h.code, "head": h.name, "lines": [{"line_code": ln.code, "line": ln.name, "budget": B.line_total(ln),
             "tds_code": m.get((h.code, ln.code))} for ln in h.lines]} for h in B.section_heads(y, "expense")]


@router.put("/lines")
def put_line_code(body: LineTdsIn, db: Session = Depends(get_db), user: User = Depends(manager)):
    x = db.scalar(select(LineTds).where(LineTds.head_code == body.head_code, LineTds.line_code == body.line_code))
    if not body.tds_code:
        if x:
            db.delete(x)
    else:
        if not db.scalar(select(TdsSection).where(TdsSection.code == body.tds_code)):
            raise HTTPException(422, "That TDS category does not exist.")
        if not x:
            x = LineTds(head_code=body.head_code, line_code=body.line_code)
            db.add(x)
        x.tds_code = body.tds_code
    B.log(db, user, f"TDS category for a budget line set to {body.tds_code or 'none'}", key=f"linetds:{body.head_code}:{body.line_code}")
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- report
@router.get("/report")
def report(fy: int, db: Session = Depends(get_db), _=Depends(viewer)):
    return T.report(db, fy)


@router.get("/budget")
def budgeted(year_id: int, db: Session = Depends(get_db), _=Depends(viewer)):
    return T.budgeted(db, B.get_year(db, year_id))


@router.get("/report.csv")
def report_csv(fy: int, db: Session = Depends(get_db), _=Depends(viewer)):
    r = T.report(db, fy)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Payee", "PAN", "Category", "Section (2025 Act)", "Old section", "Payments", "Paid (₹)", "Threshold", "TDS applies on (₹)",
                "Rate %", "Rate note", "Should be deducted (₹)", "Deducted (₹)", "Short (₹)", "Status"])
    for x in r["rows"]:
        w.writerow([x["party"], x["pan"], x["label"], x["new_ref"], x["old_ref"], x["payments"], x["gross"], x["limit"], x["taxable"],
                    x["rate"], x["rate_note"], x["expected"], x["deducted"], x["short"], x["status"]])
    w.writerow([])
    w.writerow(["Month", "Deducted (₹)", "Deposited (₹)", "Pending (₹)", "Due by", "Status"])
    for m in r["months"]:
        w.writerow([MONTHS[m["month"]], m["deducted"], m["paid"], m["pending"], m["due"], m["status"]])
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="tds-report-{fy}-{str(fy + 1)[2:]}.csv"'})


# ---------------------------------------------------------------- deposits and returns
@router.post("/deposits")
def add_deposit(body: DepositIn, db: Session = Depends(get_db), user: User = Depends(manager)):
    if not 0 <= body.month <= 11 or body.amount <= 0:
        raise HTTPException(422, "Choose the month and enter the amount paid.")
    A.fy_of(body.paid_on)
    db.add(TdsDeposit(fy_start=body.fy, month=body.month, amount=Decimal(str(round(body.amount, 2))), paid_on=body.paid_on[:10],
                      challan=body.challan.strip()[:40], created_by_name=user.name))
    B.log(db, user, f"TDS deposit for {MONTHS[body.month]}: ₹{body.amount:,.0f}, challan {body.challan}")
    db.commit()
    return {"ok": True}


@router.delete("/deposits/{dep_id}")
def delete_deposit(dep_id: int, db: Session = Depends(get_db), user: User = Depends(manager)):
    d = db.get(TdsDeposit, dep_id)
    if d:
        B.log(db, user, f"Removed TDS deposit ₹{float(d.amount):,.0f} for {MONTHS[d.month]}")
        db.delete(d)
        db.commit()
    return {"ok": True}


@router.post("/returns")
def file_return(body: ReturnIn, db: Session = Depends(get_db), user: User = Depends(manager)):
    if body.quarter not in (1, 2, 3, 4):
        raise HTTPException(422, "Choose the quarter.")
    A.fy_of(body.filed_on)
    r = db.scalar(select(TdsReturn).where(TdsReturn.fy_start == body.fy, TdsReturn.quarter == body.quarter))
    if not r:
        r = TdsReturn(fy_start=body.fy, quarter=body.quarter)
        db.add(r)
    r.filed_on, r.ack = body.filed_on[:10], body.ack.strip()[:40]
    B.log(db, user, f"Quarterly TDS statement Q{body.quarter} {body.fy}-{str(body.fy + 1)[2:]} filed on {body.filed_on}")
    db.commit()
    return {"ok": True}


@router.delete("/returns/{fy}/{quarter}")
def unfile_return(fy: int, quarter: int, db: Session = Depends(get_db), user: User = Depends(manager)):
    r = db.scalar(select(TdsReturn).where(TdsReturn.fy_start == fy, TdsReturn.quarter == quarter))
    if r:
        db.delete(r)
        B.log(db, user, f"Quarterly TDS statement Q{quarter} marked not filed")
        db.commit()
    return {"ok": True}
