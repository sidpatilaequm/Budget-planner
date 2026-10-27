#!/usr/bin/env python3
"""Upload a filled budget template to the Budget planner.

Uses only the Python standard library (Python 3.8 or later), so it runs on any computer with Python.

    # check the file and list any problems; nothing is saved
    python upload_budget.py --server https://budget.example.org --user ravi --year 2026 --file Budget_template_2026-27.xlsx

    # check and save
    python upload_budget.py --server https://budget.example.org --user ravi --year 2026 --file Budget_template_2026-27.xlsx --apply

The password is asked for, or read from the BUDGET_PASSWORD environment variable (for scheduled jobs).
--year is the year the financial year starts in (2026 for FY 2026-27).

Exit codes: 0 checked or saved without errors, 1 the file has errors (nothing saved),
2 sign-in, connection or usage problem.
"""
import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
import uuid


def call(server, path, token=None, body=None, files=None, method=None):
    url = server.rstrip("/") + path
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = "Bearer " + token
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if files:
        boundary = uuid.uuid4().hex
        parts = []
        for field, (name, content) in files.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{name}"\r\n'
                         "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
                         .encode() + content + b"\r\n")
        data = b"".join(parts) + f"--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method or ("POST" if data else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=120) as res:
            return res.status, json.loads(res.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get("detail")
        except Exception:
            detail = None
        return e.code, {"detail": detail if isinstance(detail, str) else f"HTTP {e.code}"}
    except urllib.error.URLError as e:
        sys.exit(f"Could not reach {server}: {e.reason}")


def main():
    p = argparse.ArgumentParser(description="Upload a filled budget template to the Budget planner.")
    p.add_argument("--server", required=True, help="Address of the planner, e.g. https://budget.example.org")
    p.add_argument("--user", required=True, help="Your username")
    p.add_argument("--year", required=True, type=int, help="Year the financial year starts in, e.g. 2026")
    p.add_argument("--file", required=True, help="The filled template (.xlsx)")
    p.add_argument("--apply", action="store_true", help="Save the changes. Without this the file is only checked.")
    a = p.parse_args()

    if not os.path.isfile(a.file):
        print(f"No such file: {a.file}", file=sys.stderr)
        return 2
    password = os.environ.get("BUDGET_PASSWORD") or getpass.getpass(f"Password for {a.user}: ")
    status, res = call(a.server, "/api/auth/login", body={"username": a.user, "password": password})
    if status != 200:
        print(f"Sign-in failed: {res.get('detail')}", file=sys.stderr)
        return 2
    token = res["token"]

    status, years = call(a.server, "/api/years", token)
    if status != 200:
        print(f"Could not list the financial years: {years.get('detail')}", file=sys.stderr)
        return 2
    year = next((y for y in years if y["start"] == a.year), None)
    if not year:
        have = ", ".join(f"{y['start']} (FY {y['label']})" for y in years)
        print(f"There is no financial year starting in {a.year}. Available: {have}", file=sys.stderr)
        return 2

    with open(a.file, "rb") as f:
        content = f.read()
    status, rep = call(a.server, f"/api/years/{year['id']}/template/upload?apply={'true' if a.apply else 'false'}",
                       token, files={"file": (os.path.basename(a.file), content)})
    if status != 200:
        print(f"Upload refused: {rep.get('detail')}", file=sys.stderr)
        return 2

    s = rep["summary"]
    print(f"FY {year['label']}: {s['updated']} lines to update, {s['added_lines']} lines and "
          f"{s['added_heads']} heads to add, {s['unchanged']} unchanged.")
    for w in rep.get("warnings", []):
        print(f"Note: {w}")
    if rep["errors"]:
        print(f"\n{len(rep['errors'])} problem(s); nothing was saved:")
        for e in rep["errors"]:
            where = f"{e['sheet']} row {e['row']}" if e.get("row") else e["sheet"]
            print(f"  {where}: {e['message']}")
        return 1
    for c in rep["changes"][:50]:
        print(f"  {c['sheet']} row {c['row']}: {c['action']} {c['head']} / {c['line']}  "
              f"{c['before']:,.2f} -> {c['after']:,.2f}")
    if len(rep["changes"]) > 50:
        print(f"  … and {len(rep['changes']) - 50} more")
    if rep["applied"]:
        print("\nSaved.")
    elif a.apply:
        print("\nNothing to save: the file matches the planner.")
    else:
        print("\nChecked only. Run again with --apply to save.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
