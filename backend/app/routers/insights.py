"""Alerts and budget simulations."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AlertDismissal, Scenario, User
from ..security import can, current_user, deny, require
from ..services import actuals as A
from ..services import alerts as AL
from ..services import budget as B
from ..services import planning as P
from ..services import simulation as SIM
from .plan_files import create_projected_year

router = APIRouter(prefix="/api", tags=["alerts", "simulations"])
sim_user = require("simulate", "view_expense", "view_income")


# ---------------------------------------------------------------- alerts
@router.get("/alerts")
def alerts(fy: int | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    items = AL.build(db, user, fy)
    return {"items": items, "count": len(items), "high": sum(1 for a in items if a["severity"] == "high")}


class DismissIn(BaseModel):
    key: str


@router.post("/alerts/dismiss")
def dismiss(body: DismissIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not db.scalar(select(AlertDismissal).where(AlertDismissal.user_id == user.id, AlertDismissal.alert_key == body.key[:160])):
        db.add(AlertDismissal(user_id=user.id, alert_key=body.key[:160]))
        db.commit()
    return {"ok": True}


@router.post("/alerts/restore")
def restore(db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.execute(delete(AlertDismissal).where(AlertDismissal.user_id == user.id))
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- simulations
def _public(r: dict) -> dict:
    return {k: v for k, v in r.items() if not k.startswith("_")}


@router.post("/simulate")
def simulate(prm: SIM.SimParams, db: Session = Depends(get_db), _=Depends(sim_user)):
    return _public(SIM.run(db, B.get_year(db, prm.from_year_id), prm))


class ScenarioIn(BaseModel):
    name: str
    params: SIM.SimParams


def scenario_out(s: Scenario) -> dict:
    return {"id": s.id, "name": s.name, "params": s.params, "created_by": s.created_by_name,
            "updated_at": s.updated_at.isoformat() + "Z"}


@router.get("/scenarios")
def list_scenarios(db: Session = Depends(get_db), _=Depends(sim_user)):
    return [scenario_out(s) for s in db.scalars(select(Scenario).order_by(Scenario.updated_at.desc()))]


@router.post("/scenarios")
def add_scenario(body: ScenarioIn, db: Session = Depends(get_db), user: User = Depends(sim_user)):
    if not body.name.strip():
        raise HTTPException(422, "Name the scenario.")
    B.get_year(db, body.params.from_year_id)
    s = Scenario(name=body.name.strip()[:120], params=body.params.model_dump(), created_by_name=user.name)
    db.add(s)
    B.log(db, user, f"Saved simulation “{s.name}”")
    db.commit()
    return scenario_out(s)


@router.put("/scenarios/{sid}")
def put_scenario(sid: int, body: ScenarioIn, db: Session = Depends(get_db), user: User = Depends(sim_user)):
    s = db.get(Scenario, sid)
    if not s:
        raise HTTPException(404, "That scenario no longer exists.")
    s.name, s.params = body.name.strip()[:120] or s.name, body.params.model_dump()
    B.log(db, user, f"Changed simulation “{s.name}”", key=f"scenario:{s.id}")
    db.commit()
    return scenario_out(s)


@router.delete("/scenarios/{sid}")
def delete_scenario(sid: int, db: Session = Depends(get_db), user: User = Depends(sim_user)):
    s = db.get(Scenario, sid)
    if s:
        B.log(db, user, f"Deleted simulation “{s.name}”")
        db.delete(s)
        db.commit()
    return {"ok": True}


class CompareIn(BaseModel):
    ids: list[int]


@router.post("/scenarios/compare")
def compare(body: CompareIn, db: Session = Depends(get_db), _=Depends(sim_user)):
    out = []
    for sid in body.ids[:4]:
        s = db.get(Scenario, sid)
        if s:
            prm = SIM.SimParams(**s.params)
            out.append({"id": s.id, "name": s.name, **_public(SIM.run(db, B.get_year(db, prm.from_year_id), prm))})
    return out


class ApplyIn(BaseModel):
    replace: bool = False


@router.post("/scenarios/{sid}/apply")
def apply(sid: int, body: ApplyIn, db: Session = Depends(get_db), user: User = Depends(sim_user)):
    """Creates next year's budget from a scenario: its projected amounts, with amount adjustments as new lines."""
    if not can(user, "plan_year"):
        deny("Creating a budget year needs “Plan next year”.")
    s = db.get(Scenario, sid)
    if not s:
        raise HTTPException(404, "That scenario no longer exists.")
    prm = SIM.SimParams(**s.params)
    src = B.get_year(db, prm.from_year_id)
    r = SIM.run(db, src, prm)
    req = P.PlanRequest(from_year_id=prm.from_year_id, exp=prm.exp, inc=prm.inc, qty=prm.qty, head=prm.head, item=prm.item,
                        basis=prm.basis, upto=prm.upto, carry=False)
    proj, ep = P.project(src, req, A.base_months(db, src, prm.basis, prm.upto))
    for lid, m in r["_lines"].items():
        proj[lid]["m"] = m
    y, _ = create_projected_year(db, user, src, proj, ep, req, body.replace, r["_extra"])
    B.log(db, user, f"Created FY {y.label} from simulation “{s.name}”")
    db.commit()
    return {"year": B.year_out(y)}
