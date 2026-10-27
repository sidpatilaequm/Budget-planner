"""Templates and upload: download every head and line as an Excel template, fill it in, upload it back."""
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security import can, current_user, deny
from ..services import budget as B
from ..services.template import TemplateError, build_template, process_upload, read_template

router = APIRouter(prefix="/api", tags=["templates"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SCRIPT = Path(__file__).resolve().parents[1] / "resources" / "upload_budget.py"


@router.get("/years/{year_id}/template")
def download_template(year_id: int, amounts: bool = True, db: Session = Depends(get_db),
                      user: User = Depends(current_user)):
    y = B.get_year(db, year_id)
    sections = [s for s in ("expense", "income") if can(user, f"view_{s}")]
    if not sections:
        deny("Your role cannot view any budget section.")
    data = build_template(y, sections, with_amounts=amounts)
    B.log(db, user, f"Downloaded the budget template for FY {y.label}{'' if amounts else ' (headings only)'}")
    db.commit()
    name = f"Budget_template_{y.label}{'' if amounts else '_blank'}.xlsx"
    return Response(data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/years/{year_id}/template/upload")
async def upload_template(year_id: int, apply: bool = False, file: UploadFile = File(...),
                          db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Checks the file (apply=false) or checks and saves it (apply=true). Nothing is saved if any row has an error."""
    if not (can(user, "edit_expense") or can(user, "edit_income")):
        deny("Your role cannot change budget amounts, so it cannot upload a template.")
    y = B.get_year(db, year_id)
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "The file is larger than 10 MB.")
    try:
        parsed = read_template(data)
    except TemplateError as e:
        raise HTTPException(422, str(e))
    report = process_upload(db, user, y, parsed, apply)
    s = report["summary"]
    changed = s["updated"] + s["added_lines"] + s["added_heads"]
    applied = apply and not report["errors"] and changed > 0
    if applied:
        B.log(db, user, f"Uploaded “{file.filename}” into FY {y.label}: {s['updated']} lines updated, "
                        f"{s['added_lines']} lines and {s['added_heads']} heads added")
        db.commit()
    else:
        db.rollback()
    return {"applied": applied, "year": B.year_out(y), "file": file.filename, **report,
            "changes": report["changes"][:1000]}


@router.get("/tools/upload_budget.py")
def upload_program(_: User = Depends(current_user)):
    """The command-line upload program, for uploading templates from a script or a scheduled job."""
    return Response(SCRIPT.read_text(encoding="utf-8"), media_type="text/x-python",
                    headers={"Content-Disposition": 'attachment; filename="upload_budget.py"'})
