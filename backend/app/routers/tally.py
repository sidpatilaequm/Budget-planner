"""Tally integration: connection settings, the integration key for the bridge, sync and ledger mapping."""
import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ActualEntry, LedgerMap, Setting, TdsSection, User
from ..security import require
from ..services import actuals as A
from ..services import budget as B
from ..services import tally as TL

router = APIRouter(prefix="/api/tally", tags=["tally"])
admin = require("manage_integration")
BRIDGE = Path(__file__).resolve().parents[2] / "tools" / "tally_bridge.py"


def _settings(db: Session) -> Setting:
    s = db.get(Setting, "tally")
    if not s:
        s = Setting(key="tally", value={})
        db.add(s)
        db.flush()
    return s


def _save(db: Session, s: Setting, **kw):
    s.value = {**(s.value or {}), **kw}          # new dict so the JSON column is saved


def _public(v: dict) -> dict:
    return {"host": v.get("host", ""), "port": v.get("port", 9000), "company": v.get("company", ""),
            "has_key": bool(v.get("key_hash")), "key_hint": v.get("key_hint", ""), "last_sync": v.get("last_sync"),
            "last_result": v.get("last_result"), "last_via": v.get("last_via")}


class SettingsIn(BaseModel):
    host: str = ""
    port: int = 9000
    company: str = ""


class SyncIn(BaseModel):
    date_from: str
    date_to: str


class PushIn(BaseModel):
    date_from: str | None = None
    date_to: str | None = None
    vouchers: list[dict] = Field(default_factory=list)
    ledgers: list[dict] | None = None


class MapIn(BaseModel):
    ledger_name: str
    section: str                      # expense | income | tds | ignore
    head_code: str | None = None
    line_code: str | None = None
    tds_code: str | None = None


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _=Depends(admin)):
    return _public(_settings(db).value or {})


@router.put("/settings")
def put_settings(body: SettingsIn, db: Session = Depends(get_db), user: User = Depends(admin)):
    s = _settings(db)
    _save(db, s, host=body.host.strip(), port=int(body.port or 9000), company=body.company.strip())
    B.log(db, user, "Changed the Tally connection settings")
    db.commit()
    return _public(s.value)


@router.post("/key")
def new_key(db: Session = Depends(get_db), user: User = Depends(admin)):
    """A new integration key for the bridge. Shown once; only its hash is stored. The old key stops working."""
    key = "tb_" + secrets.token_urlsafe(32)
    s = _settings(db)
    _save(db, s, key_hash=hashlib.sha256(key.encode()).hexdigest(), key_hint=key[-4:])
    B.log(db, user, "Created a new Tally integration key")
    db.commit()
    return {"key": key}


def _record(db: Session, s: Setting, res: dict, via: str):
    _save(db, s, last_sync=datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z", last_via=via,
          last_result={k: res[k] for k in ("vouchers", "entries", "removed")} | {"unmapped": len(res["unmapped"])})


@router.post("/test")
def test(db: Session = Depends(get_db), _=Depends(admin)):
    v = _settings(db).value or {}
    try:
        ledgers = TL.parse_ledgers(TL.post(v.get("host", ""), v.get("port", 9000), TL.ledger_request(v.get("company", "")), timeout=15))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Tally did not answer: {e}. Check that Tally is open with the company loaded, "
                                 "that it acts as a server on that port, and that this server can reach it.")
    _save(db, _settings(db), ledgers=[{"name": x["name"], "parent": x["parent"]} for x in ledgers][:5000])
    db.commit()
    return {"ok": True, "ledgers": len(ledgers)}


@router.post("/sync")
def sync(body: SyncIn, db: Session = Depends(get_db), user: User = Depends(admin)):
    s = _settings(db)
    v = s.value or {}
    try:
        xml = TL.post(v.get("host", ""), v.get("port", 9000), TL.voucher_request(v.get("company", ""), body.date_from, body.date_to), timeout=120)
        vouchers = TL.parse_vouchers(xml)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Tally did not answer: {e}")
    res = A.ingest_vouchers(db, vouchers, body.date_from, body.date_to, user)
    _record(db, s, res, "direct")
    db.commit()
    return res


def bridge_auth(x_api_key: str = Header(""), db: Session = Depends(get_db)) -> Setting:
    s = db.get(Setting, "tally")
    h = (s.value or {}).get("key_hash") if s else None
    if not h or not x_api_key or not hmac.compare_digest(hashlib.sha256(x_api_key.encode()).hexdigest(), h):
        raise HTTPException(401, "Integration key not valid.")
    return s


@router.post("/push")
async def push(request: Request, db: Session = Depends(get_db), s: Setting = Depends(bridge_auth)):
    """Called by the Tally bridge. JSON {date_from, date_to, vouchers, ledgers}, or Tally's raw XML answer
    with ?date_from=…&date_to=… in the address."""
    if "xml" in (request.headers.get("content-type") or ""):
        raw = await request.body()
        try:
            body = PushIn(date_from=request.query_params.get("date_from"), date_to=request.query_params.get("date_to"), vouchers=TL.parse_vouchers(raw))
        except ValueError as e:
            raise HTTPException(422, str(e))
    else:
        body = PushIn(**(await request.json()))
    if body.ledgers is not None:
        _save(db, s, ledgers=[{"name": str(x.get("name", "")), "parent": str(x.get("parent", ""))} for x in body.ledgers][:5000])
    res = A.ingest_vouchers(db, body.vouchers, body.date_from, body.date_to, None)
    _record(db, s, res, "bridge")
    db.commit()
    return res


@router.get("/bridge")
def bridge_script(_=Depends(admin)):
    return Response(BRIDGE.read_text(encoding="utf-8"), media_type="text/x-python",
                    headers={"Content-Disposition": 'attachment; filename="tally_bridge.py"'})


# ---------------------------------------------------------------- ledger mapping
@router.get("/ledgers")
def ledgers(db: Session = Depends(get_db), _=Depends(admin)):
    maps = db.scalars(select(LedgerMap).order_by(LedgerMap.ledger_name)).all()
    pending = db.execute(select(ActualEntry.ledger_name, func.count(ActualEntry.id), func.sum(ActualEntry.amount))
                         .where(ActualEntry.section == "unmapped").group_by(ActualEntry.ledger_name)).all()
    known = {m.ledger_name.lower() for m in maps}
    tally_ledgers = [x for x in ((_settings(db).value or {}).get("ledgers") or []) if x["name"].lower() not in known]
    return {"maps": [{"id": m.id, "ledger_name": m.ledger_name, "section": m.section, "head_code": m.head_code,
                      "line_code": m.line_code, "tds_code": m.tds_code} for m in maps],
            "pending": [{"ledger_name": n, "entries": c, "amount": float(a or 0)} for n, c, a in pending],
            "tally_ledgers": tally_ledgers}


@router.put("/maps")
def put_map(body: MapIn, db: Session = Depends(get_db), user: User = Depends(admin)):
    if body.section not in ("expense", "income", "tds", "ignore"):
        raise HTTPException(422, "Choose expense, income, TDS or ignore.")
    if body.section in ("expense", "income") and not (body.head_code and body.line_code):
        raise HTTPException(422, "Choose the budget line.")
    if body.tds_code and not db.scalar(select(TdsSection).where(TdsSection.code == body.tds_code)):
        raise HTTPException(422, "That TDS category does not exist.")
    name = body.ledger_name.strip()
    m = db.scalar(select(LedgerMap).where(LedgerMap.ledger_name == name))
    if not m:
        m = LedgerMap(ledger_name=name)
        db.add(m)
    m.section = body.section
    m.head_code, m.line_code = (body.head_code, body.line_code) if body.section in ("expense", "income") else (None, None)
    m.tds_code = body.tds_code if body.section in ("expense", "tds") else None
    db.flush()
    n = A.remap_ledger(db, m)
    B.log(db, user, f"Mapped Tally ledger “{name}” to {body.section}" + (f", {n} entries updated" if n else ""))
    db.commit()
    return {"ok": True, "updated": n}


@router.delete("/maps/{map_id}")
def delete_map(map_id: int, db: Session = Depends(get_db), user: User = Depends(admin)):
    m = db.get(LedgerMap, map_id)
    if not m:
        raise HTTPException(404, "Not found.")
    B.log(db, user, f"Removed the mapping of Tally ledger “{m.ledger_name}”")
    db.delete(m)
    db.commit()
    return {"ok": True}
