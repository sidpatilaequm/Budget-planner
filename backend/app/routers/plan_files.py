from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import FiscalYear, Line, User
from ..security import can, require
from ..services import budget as B
from ..services import planning as P
from ..services.excel import export_year, parse_workbook

router = APIRouter(prefix="/api", tags=["planning", "files"])
planner = require("plan_year", "view_expense", "view_income")


@router.post("/plan/preview")
def plan_preview(req: P.PlanRequest, db: Session = Depends(get_db), _=Depends(planner)):
    src = B.get_year(db, req.from_year_id)
    return P.preview(db, src, req, B.year_by_start(db, src.start_year + 1) is not None)


@router.post("/plan/create")
def plan_create(req: P.PlanRequest, db: Session = Depends(get_db), user: User = Depends(planner)):
    src = B.get_year(db, req.from_year_id)
    proj, ep = P.project(src, req)
    iss = P.issues(ep, req)
    if iss["count"]:
        raise HTTPException(409, "Bring every fixed budget within its amount first.")
    target = src.start_year + 1
    existing = B.year_by_start(db, target)
    if existing and not req.replace:
        raise HTTPException(409, f"FY {target}-{str(target + 1)[2:]} already exists.")
    if existing:
        db.delete(existing)
        db.flush()
    y = FiscalYear(start_year=target, limit_rule=src.limit_rule or "block")
    db.add(y)
    B.copy_year(db, src, y, with_amounts=True)
    db.flush()
    src_lines = {(l.head.section, l.head.code, l.code): l.id for h in src.heads for l in h.lines}
    for h in y.heads:
        for ln in h.lines:
            p = proj[src_lines[(h.section, h.code, ln.code)]]
            B.set_months(ln, p["m"])
            ln.qty, ln.rate = p["qty"], p["rate"]
    limits = 0
    if req.carry and can(user, "manage_limits"):
        if req.lock_total:
            y.total_limit_mode, y.total_limit_value = "amount", round(ep["TT"])
            limits += 1
        locked = {e["hd"].code: e["T"] for e in ep["heads"] if e["locked"]}
        for h in B.section_heads(y, "expense"):
            if h.code in locked:
                h.limit_mode, h.limit_value = "amount", round(locked[h.code])
                limits += 1
    B.log(db, user, f"Created FY {y.label} from FY {src.label} (expenses {req.exp or 0}%, income {req.inc or 0}%, "
                    f"students {req.qty or 0}%{f', {limits} limits set' if limits else ''})")
    db.commit()
    return {"year": B.year_out(y), "limits": limits}


@router.get("/years/{year_id}/export")
def export(year_id: int, db: Session = Depends(get_db), user: User = Depends(require("export"))):
    y = B.get_year(db, year_id)
    sections = [s for s in ("expense", "income") if can(user, f"view_{s}")]
    if not sections:
        raise HTTPException(403, "Your role does not allow viewing any budget section.")
    data = export_year(y, sections)
    B.log(db, user, f"Downloaded FY {y.label} as Excel")
    db.commit()
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="Budget_{y.label}.xlsx"'})


@router.post("/import")
async def import_excel(file: UploadFile = File(...), year_start: int | None = Query(None), replace: bool = False,
                       db: Session = Depends(get_db), user: User = Depends(require("import"))):
    data = await file.read()
    try:
        parsed = parse_workbook(data)
    except Exception:
        raise HTTPException(422, "That file could not be read as an Excel workbook.")
    if not parsed["expense"] and not parsed["income"]:
        raise HTTPException(422, "No expense or income sheet was found in that file.")
    start = parsed["start"] or year_start
    if not start:
        raise HTTPException(422, "The file does not say which year it is for. Choose a year and try again.")
    parts = " and ".join(p for p in ("expense" if parsed["expense"] else "", "income" if parsed["income"] else "") if p)
    y = B.year_by_start(db, start)
    if y and not replace:
        raise HTTPException(409, f"The {parts} heads and lines in FY {y.label} will be replaced with the ones in this file.")
    if not y:
        y = FiscalYear(start_year=start)
        db.add(y)
        B.fill_template(db, y)
        db.flush()
    for section in ("expense", "income"):
        heads = parsed[section]
        if not heads:
            continue
        old_codes = {h.name.lower(): h.code for h in B.section_heads(y, section)}
        for h in B.section_heads(y, section):
            y.heads.remove(h)  # delete-orphan removes the head and its lines
        db.flush()
        for hi, hd in enumerate(heads):
            head = B.add_head(db, y, section, hd["name"], code=old_codes.get(hd["name"].lower()), order=hi)
            for li, ln in enumerate(hd["lines"]):
                line = B.add_line(db, head, ln["name"], order=li)
                line.qty, line.rate = ln["qty"], ln["rate"]
                B.set_months(line, ln["m"])
    B.log(db, user, f"Imported {parts} from “{file.filename}” into FY {y.label}")
    db.commit()
    return {"year": B.year_out(y), "parts": parts}
