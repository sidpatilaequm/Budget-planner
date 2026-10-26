"""API tests. They run against SQLite by default; set TEST_DATABASE_URL to run against MySQL.

    pytest -q
"""
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def admin(client):
    assert client.get("/api/auth/status").json()["needs_setup"] is True
    r = client.post("/api/auth/setup", json={"name": "Ravi Kumar", "username": "ravi", "password": "secret123"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def sheet(client, token, year_id, section="expense"):
    r = client.get(f"/api/years/{year_id}/sections/{section}", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def test_setup_and_login(client, admin):
    assert client.post("/api/auth/setup", json={"name": "X", "username": "x", "password": "secret123"}).status_code == 409
    assert client.post("/api/auth/login", json={"username": "ravi", "password": "nope"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "RAVI", "password": "secret123"})
    assert r.status_code == 200 and r.json()["perms"]["manage_users"] is True
    assert client.get("/api/years").status_code == 401


def test_edit_lines_and_totals(client, admin):
    y = client.get("/api/years", headers=auth(admin)).json()[0]
    assert y["label"] == "2026-27"
    s = sheet(client, admin, y["id"])
    transport = next(h for h in s["heads"] if h["name"] == "Transport Expenses")
    office = next(h for h in s["heads"] if h["name"] == "Office Expenses")
    for ln, amt in zip(transport["lines"][:3], (10000, 5000, 20000)):
        m = [0] * 12
        m[0] = amt
        r = client.patch(f"/api/lines/{ln['id']}", json={"m": m}, headers=auth(admin))
        assert r.status_code == 200, r.text
    for ln, amt in zip(office["lines"][:2], (8000, 12000)):
        r = client.patch(f"/api/lines/{ln['id']}", json={"m": [amt] + [0] * 11}, headers=auth(admin))
        assert r.status_code == 200
    # qty x rate spreads in installments for income
    inc = sheet(client, admin, y["id"], "income")
    ln = inc["heads"][0]["lines"][1]
    r = client.patch(f"/api/lines/{ln['id']}", json={"qty": 800, "rate": 60000, "set_qty_rate": True}, headers=auth(admin))
    m = r.json()["line"]["m"]
    assert m[0] == m[4] == m[8] == 16_000_000 and sum(m) == 48_000_000
    yrs = client.get("/api/years", headers=auth(admin)).json()
    assert yrs[0]["expense"] == 55000


def test_plan_with_fixed_head_and_total(client, admin):
    y = client.get("/api/years", headers=auth(admin)).json()[0]
    s = sheet(client, admin, y["id"])
    transport = next(h for h in s["heads"] if h["name"] == "Transport Expenses")
    diesel = transport["lines"][2]
    req = {"from_year_id": y["id"], "exp": 10, "lock": {str(transport["id"]): True},
           "item": {str(diesel["id"]): 50}, "lock_total": True, "mode": "auto"}
    p = client.post("/api/plan/preview", json=req, headers=auth(admin)).json()
    ex = p["sections"]["expense"]
    t = next(h for h in ex["heads"] if h["id"] == transport["id"])
    assert round(t["proj"]) == 38500 and t["locked"]
    assert [l["proj"] for l in t["lines"][:3]] == [5667, 2833, 30000]
    assert round(ex["proj"]) == 60500 and p["issues"] == 0
    # manual mode: nothing absorbs, so the fixed head is over and creation is refused
    manual = dict(req, mode="manual")
    assert client.post("/api/plan/preview", json=manual, headers=auth(admin)).json()["issues"] == 2
    assert client.post("/api/plan/create", json=manual, headers=auth(admin)).status_code == 409
    r = client.post("/api/plan/create", json=req, headers=auth(admin))
    assert r.status_code == 200 and r.json()["limits"] == 2


def test_limits_block_increase_but_allow_decrease(client, admin):
    yrs = client.get("/api/years", headers=auth(admin)).json()
    ny = yrs[-1]
    assert ny["label"] == "2027-28" and ny["expense"] == 60500
    s = sheet(client, admin, ny["id"])
    assert s["total_limit"] == 60500
    transport = next(h for h in s["heads"] if h["name"] == "Transport Expenses")
    assert transport["limit"] == 38500
    ln = transport["lines"][0]
    m = list(ln["m"])
    m[5] += 1000
    r = client.patch(f"/api/lines/{ln['id']}", json={"m": m}, headers=auth(admin))
    assert r.status_code == 409 and "over its limit" in r.json()["detail"]
    m = list(ln["m"])
    m[0] -= 500
    assert client.patch(f"/api/lines/{ln['id']}", json={"m": m}, headers=auth(admin)).status_code == 200
    # switch to warn: the change is saved with a warning
    lim = client.put(f"/api/years/{ny['id']}/limits", json={"rule": "warn"}, headers=auth(admin)).json()
    assert lim["rule"] == "warn"
    m[6] += 2000
    r = client.patch(f"/api/lines/{ln['id']}", json={"m": m}, headers=auth(admin))
    assert r.status_code == 200 and r.json()["warning"]
    # growth-based head limit
    office = next(h for h in lim["heads"] if h["name"] == "Office Expenses")
    lim = client.put(f"/api/years/{ny['id']}/limits", json={"heads": {str(office["id"]): {"mode": "growth", "value": 5}}},
                     headers=auth(admin)).json()
    assert round(next(h for h in lim["heads"] if h["id"] == office["id"])["limit"]) == 21000


def test_department_user_scope(client, admin):
    roles = client.get("/api/roles", headers=auth(admin)).json()
    dept = next(r for r in roles if r["name"] == "Department editor")
    yrs = client.get("/api/years", headers=auth(admin)).json()
    cat = client.get(f"/api/head-catalog?year_id={yrs[0]['id']}", headers=auth(admin)).json()
    tr = next(h for h in cat if h["name"] == "Transport Expenses")
    r = client.post("/api/users", json={"name": "Transport Head", "username": "transport", "role_id": dept["id"],
                                        "password": "pass12345", "scope": "some", "heads": [tr]}, headers=auth(admin))
    assert r.status_code == 200, r.text
    tok = client.post("/api/auth/login", json={"username": "transport", "password": "pass12345"}).json()["token"]
    s = sheet(client, tok, yrs[0]["id"])
    allowed = {h["name"] for h in s["heads"] if h["can_edit"]}
    assert allowed == {"Transport Expenses"} and s["can_manage_heads"] is False
    other = next(h for h in s["heads"] if h["name"] == "Office Expenses")["lines"][0]
    assert client.patch(f"/api/lines/{other['id']}", json={"m": [1] * 12}, headers=auth(tok)).status_code == 403
    assert client.get(f"/api/years/{yrs[0]['id']}/sections/income", headers=auth(tok)).status_code == 403
    assert client.get("/api/users", headers=auth(tok)).status_code == 403
    assert client.post("/api/plan/preview", json={"from_year_id": yrs[0]["id"]}, headers=auth(tok)).status_code == 403
    # cannot remove the last administrator
    me = client.get("/api/auth/me", headers=auth(admin)).json()["user"]
    assert client.delete(f"/api/users/{me['id']}", headers=auth(admin)).status_code == 409


def test_excel_export_and_import(client, admin):
    yrs = client.get("/api/years", headers=auth(admin)).json()
    r = client.get(f"/api/years/{yrs[0]['id']}/export", headers=auth(admin))
    assert r.status_code == 200 and r.content[:2] == b"PK"
    path = os.getenv("SAMPLE_XLSX", "")
    data = open(path, "rb").read() if path and os.path.exists(path) else r.content
    files = {"file": ("Budget.xlsx", data)}
    r = client.post("/api/import", files=files, headers=auth(admin))
    assert r.status_code == 409  # year exists: asks for confirmation
    r = client.post("/api/import?replace=true", files={"file": ("Budget.xlsx", data)}, headers=auth(admin))
    assert r.status_code == 200, r.text
    s = sheet(client, admin, r.json()["year"]["id"])
    assert len(s["heads"]) == 15
    acts = client.get("/api/activity", headers=auth(admin)).json()
    assert any("Imported" in a["action"] for a in acts)
