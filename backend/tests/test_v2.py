"""Version 2: actuals, Tally, TDS, alerts and simulations. Runs on SQLite like the other tests."""
import io
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", f"sqlite:///{_tmp}/v2.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import tally as TL  # noqa: E402
from app.services import tds as T  # noqa: E402

FY = 2026


def auth(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin(client):
    r = client.post("/api/auth/setup", json={"name": "Ravi Kumar", "username": "ravi", "password": "secret123"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def year(client, admin):
    ys = client.get("/api/years", headers=auth(admin)).json()
    y = next(y for y in ys if y["start"] == FY)
    idx = client.get(f"/api/years/{y['id']}/lines-index", headers=auth(admin)).json()
    return {"id": y["id"], "idx": idx}


def line(year, section, head, ln):
    h = next(h for h in year["idx"][section] if h["name"] == head)
    return h["code"], next(x for x in h["lines"] if x["name"] == ln)["code"]


def add(client, tok, year, section, head, ln, amount, date, **kw):
    hc, lc = line(year, section, head, ln)
    return client.post("/api/actuals", headers=auth(tok), json={"date": date, "section": section, "head_code": hc, "line_code": lc, "amount": amount, **kw})


def set_budget(client, tok, year_id, section, head, ln, months):
    h = next(h for h in client.get(f"/api/years/{year_id}/sections/{section}", headers=auth(tok)).json()["heads"] if h["name"] == head)
    lid = next(x for x in h["lines"] if x["name"] == ln)["id"]
    r = client.patch(f"/api/lines/{lid}", headers=auth(tok), json={"m": months})
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------- actuals
def test_manual_actuals_and_compare(client, admin, year):
    set_budget(client, admin, year["id"], "expense", "Office Expenses", "Electricity", [20000] * 12)
    set_budget(client, admin, year["id"], "expense", "Transport Expenses", "Diesel Expenses", [150000] * 12)
    set_budget(client, admin, year["id"], "income", "NPPS – Transport", "Transport", [300000, 0, 0, 0, 300000, 0, 0, 0, 300000, 0, 0, 0])
    set_budget(client, admin, year["id"], "income", "NPPS – Tuition Fees", "Pre-Primary", [400000] * 12)
    r = add(client, admin, year, "expense", "Office Expenses", "Electricity", 18500, f"{FY}-04-12", party="MSEDCL", voucher_no="PV-1")
    assert r.status_code == 200, r.text
    assert r.json()["month"] == 0 and r.json()["fy"] == FY
    add(client, admin, year, "expense", "Office Expenses", "Electricity", 21000, f"{FY}-05-12")
    add(client, admin, year, "income", "NPPS – Transport", "Transport", 250000, f"{FY}-04-30")
    # validation
    assert add(client, admin, year, "income", "NPPS – Transport", "Transport", 1000, f"{FY}-04-30", tds_amount=10).status_code == 422
    assert add(client, admin, year, "expense", "Office Expenses", "Electricity", 100, "2031-04-01").status_code == 409
    assert client.post("/api/actuals", headers=auth(admin), json={"date": f"{FY}-04-01", "section": "expense", "head_code": "x", "line_code": "y", "amount": 5}).status_code == 422
    lst = client.get(f"/api/actuals?fy={FY}", headers=auth(admin)).json()
    assert lst["count"] == 3 and lst["totals"]["expense"] == 39500 and lst["rows"][0]["head"]
    cmp_ = client.get(f"/api/years/{year['id']}/compare/expense", headers=auth(admin)).json()
    office = next(h for h in cmp_["heads"] if h["name"] == "Office Expenses")
    assert office["actual"][0] == 18500 and office["actual"][1] == 21000 and cmp_["upto"] == 1
    # edit and delete a manual entry
    eid = lst["rows"][-1]["id"]
    hc, lc = line(year, "expense", "Office Expenses", "Electricity")
    r = client.patch(f"/api/actuals/{eid}", headers=auth(admin), json={"date": f"{FY}-04-12", "section": "expense", "head_code": hc, "line_code": lc, "amount": 19000})
    assert r.status_code == 200 and r.json()["amount"] == 19000


def test_plan_from_actuals_and_forecast(client, admin, year):
    base = {"from_year_id": year["id"], "exp": 10}
    b = client.post("/api/plan/preview", headers=auth(admin), json=base).json()
    a = client.post("/api/plan/preview", headers=auth(admin), json={**base, "basis": "actual"}).json()
    f = client.post("/api/plan/preview", headers=auth(admin), json={**base, "basis": "forecast"}).json()
    assert a["basis"] == "actual"
    # actual base: only what was booked (19,000 + 21,000) on expenses, +10%
    assert a["sections"]["expense"]["base"] == 40000 and a["sections"]["expense"]["proj"] == 44000
    # budget: 12 × (20,000 + 1,50,000); forecast: actuals for April–May, then budget for June–March
    assert b["sections"]["expense"]["base"] == 12 * 170000
    assert f["sections"]["expense"]["base"] == 40000 + 10 * 170000


def test_import_template_round_trip(client, admin, year):
    r = client.get(f"/api/years/{year['id']}/actuals-template", headers=auth(admin))
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    ws = wb["Actuals"]
    ws.append([f"{FY}-06-05", "Expense", "Printing & Stationery", "School Stationery", 12000, "Canvas Creations", "Payment", "PV-9", "", "", 0])
    ws.append([f"{FY}-06-05", "Expense", "No such head", "x", 5, "", "", "", "", "", 0])
    buf = io.BytesIO()
    wb.save(buf)
    files = {"file": ("a.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = client.post("/api/actuals/import", headers=auth(admin), files=files)
    assert r.json()["ok"] is False and r.json()["errors"] == ["Row 4: no line “x” under head “No such head”"]   # rows 2 and 3 are fine
    ws.delete_rows(4)
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post("/api/actuals/import", headers=auth(admin), files={"file": ("a.xlsx", buf.getvalue(), "application/octet-stream")})
    assert r.json() == {"ok": True, "rows": 2, "errors": []}


# ---------------------------------------------------------------- Tally
TALLY_XML = f"""<ENVELOPE><BODY><DATA><COLLECTION>
<VOUCHER REMOTEID="g-1" VCHTYPE="Journal">
  <GUID>g-1</GUID><DATE>{FY}0710</DATE><VOUCHERTYPENAME>Journal</VOUCHERTYPENAME><VOUCHERNUMBER>J-7</VOUCHERNUMBER>
  <PARTYLEDGERNAME>Grow India Facility Services</PARTYLEDGERNAME><NARRATION>Housekeeping July &amp; August</NARRATION>
  <ALLLEDGERENTRIES.LIST><LEDGERNAME>Housekeeping Charges</LEDGERNAME><ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE><AMOUNT>-150000.00</AMOUNT></ALLLEDGERENTRIES.LIST>
  <ALLLEDGERENTRIES.LIST><LEDGERNAME>TDS Payable 194C</LEDGERNAME><ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE><AMOUNT>3000.00</AMOUNT></ALLLEDGERENTRIES.LIST>
  <ALLLEDGERENTRIES.LIST><LEDGERNAME>Grow India Facility Services</LEDGERNAME><ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE><AMOUNT>147000.00</AMOUNT></ALLLEDGERENTRIES.LIST>
</VOUCHER>
<VOUCHER REMOTEID="g-2" VCHTYPE="Receipt">
  <GUID>g-2</GUID><DATE>{FY}0715</DATE><VOUCHERTYPENAME>Receipt</VOUCHERTYPENAME><VOUCHERNUMBER>R-88</VOUCHERNUMBER>
  <ALLLEDGERENTRIES.LIST><LEDGERNAME>HDFC Bank</LEDGERNAME><AMOUNT>-480000.00</AMOUNT></ALLLEDGERENTRIES.LIST>
  <ALLLEDGERENTRIES.LIST><LEDGERNAME>Tuition Fees - Pre-Primary</LEDGERNAME><AMOUNT>480000.00</AMOUNT></ALLLEDGERENTRIES.LIST>
</VOUCHER>
<VOUCHER REMOTEID="g-3" VCHTYPE="Payment"><GUID>g-3</GUID><DATE>{FY}0716</DATE><ISCANCELLED>Yes</ISCANCELLED>
  <ALLLEDGERENTRIES.LIST><LEDGERNAME>Housekeeping Charges</LEDGERNAME><AMOUNT>-999.00</AMOUNT></ALLLEDGERENTRIES.LIST></VOUCHER>
</COLLECTION></DATA></BODY></ENVELOPE>"""


def test_tally_parser():
    vs = TL.parse_vouchers(TALLY_XML.encode())
    assert len(vs) == 2                                         # the cancelled voucher is left out
    assert vs[0]["date"] == f"{FY}0710" and vs[0]["narration"] == "Housekeeping July & August"
    assert [e["amount"] for e in vs[0]["entries"]] == [-150000.0, 3000.0, 147000.0]
    assert "<SVFROMDATE>20260401</SVFROMDATE>" in TL.voucher_request("My School", "2026-04-01", "2026-04-30")
    assert TL.parse_ledgers(b'<ENVELOPE><LEDGER NAME="Cash"><PARENT>Cash-in-Hand</PARENT></LEDGER></ENVELOPE>') == [{"name": "Cash", "parent": "Cash-in-Hand"}]


def test_tally_push_mapping_and_tds(client, admin, year):
    assert client.post("/api/tally/push", json={"vouchers": []}).status_code == 401
    key = client.post("/api/tally/key", headers=auth(admin)).json()["key"]
    assert client.post("/api/tally/push", headers={"X-Api-Key": "wrong"}, json={"vouchers": []}).status_code == 401
    rng = f"?date_from={FY}-07-01&date_to={FY}-07-31"
    r = client.post("/api/tally/push" + rng, headers={"X-Api-Key": key, "Content-Type": "application/xml"}, content=TALLY_XML)
    assert r.status_code == 200, r.text
    assert set(r.json()["unmapped"]) == {"Housekeeping Charges", "TDS Payable 194C", "Grow India Facility Services", "HDFC Bank", "Tuition Fees - Pre-Primary"}
    led = client.get("/api/tally/ledgers", headers=auth(admin)).json()
    assert len(led["pending"]) == 5
    hc, lc = line(year, "expense", "Security and Housekeeping", "Grow India")
    ic, il = line(year, "income", "NPPS – Tuition Fees", "Pre-Primary")
    maps = [{"ledger_name": "Housekeeping Charges", "section": "expense", "head_code": hc, "line_code": lc, "tds_code": "CONTRACT"},
            {"ledger_name": "TDS Payable 194C", "section": "tds", "tds_code": "CONTRACT"},
            {"ledger_name": "Grow India Facility Services", "section": "ignore"}, {"ledger_name": "HDFC Bank", "section": "ignore"},
            {"ledger_name": "Tuition Fees - Pre-Primary", "section": "income", "head_code": ic, "line_code": il}]
    for m in maps:
        assert client.put("/api/tally/maps", headers=auth(admin), json=m).status_code == 200
    assert client.get("/api/tally/ledgers", headers=auth(admin)).json()["pending"] == []
    # sync again: now exact, with the TDS from the voucher on the expense
    r = client.post("/api/tally/push" + rng, headers={"X-Api-Key": key, "Content-Type": "application/xml"}, content=TALLY_XML)
    assert r.json()["unmapped"] == [] and r.json()["entries"] == 2
    rows = client.get(f"/api/actuals?fy={FY}&source=tally", headers=auth(admin)).json()["rows"]
    hk = next(x for x in rows if x["section"] == "expense")
    assert hk["amount"] == 150000 and hk["tds_amount"] == 3000 and hk["tds_code"] == "CONTRACT" and hk["party"] == "Grow India Facility Services"
    assert next(x for x in rows if x["section"] == "income")["amount"] == 480000
    # Tally entries cannot be changed here
    assert client.delete(f"/api/actuals/{hk['id']}", headers=auth(admin)).status_code == 409
    # a voucher deleted in Tally disappears on the next sync of that period
    only_receipt = TALLY_XML.split('<VOUCHER REMOTEID="g-1"')[0] + '<VOUCHER REMOTEID="g-2"' + TALLY_XML.split('<VOUCHER REMOTEID="g-2"')[1]
    r = client.post("/api/tally/push" + rng, headers={"X-Api-Key": key, "Content-Type": "application/xml"}, content=only_receipt)
    assert r.json()["removed"] == 1
    st = client.get("/api/tally/settings", headers=auth(admin)).json()
    assert st["has_key"] and st["last_via"] == "bridge" and st["last_result"]["vouchers"] == 1
    # restore the July voucher for the TDS tests
    client.post("/api/tally/push" + rng, headers={"X-Api-Key": key, "Content-Type": "application/xml"}, content=TALLY_XML)


def test_bridge_download(client, admin):
    r = client.get("/api/tally/bridge", headers=auth(admin))
    assert r.status_code == 200 and "def run_once" in r.text


# ---------------------------------------------------------------- TDS
def test_tds_rules(client, admin, year):
    # contractor: 150,000 in one payment with 3,000 deducted (2% for a company) -> fine once the PAN says company
    r = client.put("/api/tds/parties", headers=auth(admin), json={"name": "Grow India Facility Services", "pan": "AABCG1234K"})
    assert r.json()["kind"] == "other"
    assert client.put("/api/tds/parties", headers=auth(admin), json={"name": "X", "pan": "BAD"}).status_code == 422
    # professional: Adv. Ashwini Gole, no PAN, 3 × 20,000 = 60,000 > 50,000, nothing deducted -> short at 20%
    for d in ("08-05", "09-05", "10-05"):
        add(client, admin, year, "expense", "Consultant Charges", "Adv. Ashwini Gole", 20000, f"{FY}-{d}", party="Adv. Ashwini Gole", tds_code="PROF")
    # contractor below the limits but close: 85,000 in three payments of under 30,000 -> near
    for d in ("08-10", "09-10", "10-10"):
        add(client, admin, year, "expense", "Transport Expenses", "Maintenance", 28333, f"{FY}-{d}", party="Shree Motors", tds_code="CONTRACT")
    # rent above ₹50,000 a month, deducted correctly
    client.put("/api/tds/parties", headers=auth(admin), json={"name": "Undri Estates", "pan": "ABCPD1234E"})
    add(client, admin, year, "expense", "Undri School Expenses", "Undri School (Rent)", 90000, f"{FY}-08-01", party="Undri Estates", tds_code="RENT_LB", tds_amount=9000)
    rep = client.get(f"/api/tds/report?fy={FY}", headers=auth(admin)).json()
    by = {(x["party"], x["code"]): x for x in rep["rows"]}
    g = by[("Grow India Facility Services", "CONTRACT")]
    assert g["status"] == "ok" and g["expected"] == 3000 and g["rate"] == 2
    a = by[("Adv. Ashwini Gole", "PROF")]
    assert a["status"] == "short" and a["rate"] == 20 and a["rate_note"] == "no PAN" and a["expected"] == 12000
    assert by[("Shree Motors", "CONTRACT")]["status"] == "near"
    u = by[("Undri Estates", "RENT_LB")]
    assert u["status"] == "ok" and u["expected"] == 9000
    # deposits: July's 3,000 and August's 9,000 deducted; due dates 7 Aug and 7 Sep
    m = {x["month"]: x for x in rep["months"]}
    assert m[3]["deducted"] == 3000 and m[3]["due"] == f"{FY}-08-07" and m[4]["due"] == f"{FY}-09-07"
    assert T.deposit_due(FY, 11) == f"{FY + 1}-04-30" and T.deposit_due(FY, 8) == f"{FY + 1}-01-07"
    client.post("/api/tds/deposits", headers=auth(admin), json={"fy": FY, "month": 3, "amount": 3000, "paid_on": f"{FY}-08-05", "challan": "00042"})
    rep = client.get(f"/api/tds/report?fy={FY}", headers=auth(admin)).json()
    assert rep["months"][3]["status"] == "paid" and rep["months"][4]["status"] == "overdue"
    assert rep["quarters"][1]["due"] == f"{FY}-10-31"
    assert client.get(f"/api/tds/report.csv?fy={FY}", headers=auth(admin)).text.count("Adv. Ashwini Gole") == 1


def test_budgeted_tds(client, admin, year):
    hc, lc = line(year, "expense", "Consultant Charges", "Parag Erande")
    assert client.put("/api/tds/lines", headers=auth(admin), json={"head_code": hc, "line_code": lc, "tds_code": "PROF"}).status_code == 200
    b = client.get(f"/api/tds/budget?year_id={year['id']}", headers=auth(admin)).json()
    row = next(x for x in b["lines"] if x["line"] == "Parag Erande")
    assert row["rate"] == 10 and row["tds"] == round(row["budget"] * 0.10)
    lines = client.get(f"/api/tds/lines?year_id={year['id']}", headers=auth(admin)).json()
    assert any(x["tds_code"] == "PROF" for h in lines for x in h["lines"])


def test_alerts(client, admin):
    a = client.get(f"/api/alerts?fy={FY}", headers=auth(admin)).json()
    titles = " | ".join(x["title"] for x in a["items"])
    assert "TDS short by ₹12,000: Adv. Ashwini Gole" in titles
    assert "No PAN for Adv. Ashwini Gole" in titles
    assert "Shree Motors is close to the TDS threshold" in titles
    assert "TDS for August overdue" in titles
    key = next(x["key"] for x in a["items"] if x["title"].startswith("No PAN"))
    client.post("/api/alerts/dismiss", headers=auth(admin), json={"key": key})
    assert all(x["key"] != key for x in client.get(f"/api/alerts?fy={FY}", headers=auth(admin)).json()["items"])
    client.post("/api/alerts/restore", headers=auth(admin))
    assert any(x["key"] == key for x in client.get(f"/api/alerts?fy={FY}", headers=auth(admin)).json()["items"])


# ---------------------------------------------------------------- simulations
def test_simulation(client, admin, year):
    tr = next(h for h in client.get(f"/api/years/{year['id']}/sections/expense", headers=auth(admin)).json()["heads"] if h["name"] == "Transport Expenses")
    prm = {"from_year_id": year["id"], "inc": 8, "exp": 5, "opening_cash": 5000000, "collection": 90,
           "adjustments": [{"label": "New bus loan EMI", "section": "expense", "head_id": tr["id"], "kind": "amount", "value": 1200000, "month_from": 6, "month_to": 11},
                           {"label": "Diesel up", "section": "expense", "head_id": tr["id"], "kind": "pct", "value": 10}]}
    r = client.post("/api/simulate", headers=auth(admin), json=prm)
    assert r.status_code == 200, r.text
    s = r.json()
    trs = next(h for h in s["heads"]["expense"] if h["name"] == "Transport Expenses")
    assert trs["sim"] > trs["base"] * 1.05 and sum(trs["months"][6:]) > sum(trs["months"][:6])
    assert s["cash_in"][0] == round(s["income"][0] * 0.9) and len(s["closing"]) == 12
    assert s["closing"][0] == round(5000000 + s["income"][0] * 0.9 - s["expense"][0])
    sid = client.post("/api/scenarios", headers=auth(admin), json={"name": "Fees +8%, new buses", "params": prm}).json()["id"]
    sid2 = client.post("/api/scenarios", headers=auth(admin), json={"name": "Flat", "params": {"from_year_id": year["id"]}}).json()["id"]
    cmp_ = client.post("/api/scenarios/compare", headers=auth(admin), json={"ids": [sid, sid2]}).json()
    assert [c["name"] for c in cmp_] == ["Fees +8%, new buses", "Flat"] and cmp_[0]["totals"]["income"] > cmp_[1]["totals"]["income"]
    r = client.post(f"/api/scenarios/{sid}/apply", headers=auth(admin), json={})
    assert r.status_code == 200, r.text
    ny = r.json()["year"]
    exp = client.get(f"/api/years/{ny['id']}/sections/expense", headers=auth(admin)).json()
    tr_new = next(h for h in exp["heads"] if h["name"] == "Transport Expenses")
    emi = next(x for x in tr_new["lines"] if x["name"] == "New bus loan EMI")
    assert sum(emi["m"]) == 1200000 and emi["m"][5] == 0
    assert client.post(f"/api/scenarios/{sid}/apply", headers=auth(admin), json={}).status_code == 409   # year exists now


# ---------------------------------------------------------------- permissions
def test_permissions(client, admin, year):
    roles = {r["name"]: r for r in client.get("/api/roles", headers=auth(admin)).json()}
    viewer = roles["Viewer"]["id"]
    r = client.post("/api/users", headers=auth(admin), json={"name": "Vee", "username": "vee", "password": "secret123", "role_id": viewer, "scope": "all", "active": True})
    assert r.status_code == 200, r.text
    tok = client.post("/api/auth/login", json={"username": "vee", "password": "secret123"}).json()["token"]
    assert client.get(f"/api/actuals?fy={FY}", headers=auth(tok)).status_code == 200            # viewer can see
    assert client.get(f"/api/tds/report?fy={FY}", headers=auth(tok)).status_code == 200
    assert add(client, tok, year, "expense", "Office Expenses", "Electricity", 5, f"{FY}-04-01").status_code == 403
    assert client.post("/api/tally/key", headers=auth(tok)).status_code == 403
    assert client.post("/api/simulate", headers=auth(tok), json={"from_year_id": year["id"]}).status_code == 403
    assert client.put("/api/tds/parties", headers=auth(tok), json={"name": "Z"}).status_code == 403
    titles = [a["area"] for a in client.get(f"/api/alerts?fy={FY}", headers=auth(tok)).json()["items"]]
    assert "Tally" not in titles                                                              # viewer has no Tally setup rights
