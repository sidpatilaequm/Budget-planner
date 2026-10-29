"""
Tally bridge for Budget Planner.

Runs on the computer where Tally Prime (or Tally.ERP 9) is open. It asks Tally for this financial
year's vouchers and ledgers and sends them to Budget Planner, so the planner shows actual income and
expenses without anyone typing them in. Only Python 3.9+ is needed; no other installation.

1. In Tally: F1 Help > Settings > Connectivity > Client/Server configuration:
   "TallyPrime acts as" = Both (or Server), Port = 9000. Keep the company open.
2. In Budget Planner: Actuals > Tally > Create integration key. Copy the key.
3. On the Tally computer, run once to test:
       python tally_bridge.py --app https://budget.example.com --key tb_xxxx --company "My School"
   then every 15 minutes, for example with Windows Task Scheduler, or leave it running with:
       python tally_bridge.py --app ... --key ... --company "..." --every 15

The key can also be given in the environment variable BUDGET_PLANNER_KEY instead of --key.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

BAD = re.compile(r"&#(?:[0-8]|1[0-9]|2[0-9]|3[01]);|[\x00-\x08\x0b\x0c\x0e-\x1f]")


def esc(s):
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def tally(url, body, timeout=180):
    req = urllib.request.Request(url, data=body.encode("utf-8"), headers={"Content-Type": "text/xml; charset=utf-8"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return ET.fromstring(BAD.sub("", r.read().decode("utf-8", "replace")))


def t(el, tag):
    x = el.find(tag)
    return (x.text or "").strip() if x is not None and x.text else ""


def num(s):
    m = re.match(r"^-?\d+(\.\d+)?", (s or "").replace(",", "").strip())
    return float(m.group(0)) if m else 0.0


def ledgers(url, company):
    co = f"<SVCURRENTCOMPANY>{esc(company)}</SVCURRENTCOMPANY>" if company else ""
    root = tally(url, f"""<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>BPLedgers</ID></HEADER>
<BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>{co}</STATICVARIABLES><TDL><TDLMESSAGE>
<COLLECTION NAME="BPLedgers" ISMODIFY="No"><TYPE>Ledger</TYPE><FETCH>NAME, PARENT</FETCH></COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>""")
    return [{"name": le.get("NAME") or t(le, "NAME"), "parent": t(le, "PARENT")} for le in root.iter("LEDGER") if le.get("NAME") or t(le, "NAME")]


def vouchers(url, company, d_from, d_to):
    co = f"<SVCURRENTCOMPANY>{esc(company)}</SVCURRENTCOMPANY>" if company else ""
    root = tally(url, f"""<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>BPVouchers</ID></HEADER>
<BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT><SVFROMDATE>{d_from:%Y%m%d}</SVFROMDATE><SVTODATE>{d_to:%Y%m%d}</SVTODATE>{co}</STATICVARIABLES>
<TDL><TDLMESSAGE><COLLECTION NAME="BPVouchers" ISMODIFY="No"><TYPE>Voucher</TYPE>
<FETCH>GUID, DATE, VOUCHERTYPENAME, VOUCHERNUMBER, PARTYLEDGERNAME, NARRATION, ISCANCELLED, ISOPTIONAL, ALLLEDGERENTRIES.LIST, LEDGERENTRIES.LIST</FETCH>
<FILTER>BPNotCancelled</FILTER></COLLECTION><SYSTEM TYPE="Formulae" NAME="BPNotCancelled">NOT $IsCancelled AND NOT $IsOptional</SYSTEM>
</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>""")
    out = []
    for v in root.iter("VOUCHER"):
        if t(v, "ISCANCELLED").lower() == "yes" or t(v, "ISOPTIONAL").lower() == "yes":
            continue
        entries = [{"ledger": t(le, "LEDGERNAME"), "amount": num(t(le, "AMOUNT"))}
                   for tag in ("ALLLEDGERENTRIES.LIST", "LEDGERENTRIES.LIST") for le in v.findall(tag) if t(le, "LEDGERNAME")]
        out.append({"guid": t(v, "GUID") or v.get("REMOTEID") or "", "date": t(v, "DATE"), "type": t(v, "VOUCHERTYPENAME") or v.get("VCHTYPE") or "",
                    "number": t(v, "VOUCHERNUMBER"), "party": t(v, "PARTYLEDGERNAME"), "narration": t(v, "NARRATION"), "entries": entries})
    return out


def push(app, key, payload):
    req = urllib.request.Request(app.rstrip("/") + "/api/tally/push", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "X-Api-Key": key}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))


def fy_start(today):
    return dt.date(today.year if today.month >= 4 else today.year - 1, 4, 1)


def month_chunks(a, b):
    """Month by month, so Tally never has to send one huge answer."""
    cur = a
    while cur <= b:
        nxt = (cur.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        yield cur, min(b, nxt - dt.timedelta(days=1))
        cur = nxt


def run_once(a):
    today = dt.date.today()
    d_from = dt.date.fromisoformat(a.date_from) if a.date_from else fy_start(today)
    d_to = dt.date.fromisoformat(a.date_to) if a.date_to else today
    tally_url = f"http://{a.tally_host}:{a.tally_port}"
    first = True
    for c_from, c_to in month_chunks(d_from, d_to):
        vs = vouchers(tally_url, a.company, c_from, c_to)
        payload = {"date_from": c_from.isoformat(), "date_to": c_to.isoformat(), "vouchers": vs}
        if first:
            payload["ledgers"] = ledgers(tally_url, a.company)
            first = False
        res = push(a.app, a.key, payload)
        print(f"{c_from:%b %Y}: {res['vouchers']} vouchers, {res['entries']} entries"
              f"{', ' + str(res['removed']) + ' removed' if res.get('removed') else ''}"
              f"{', ' + str(len(res['unmapped'])) + ' ledgers to map in Budget Planner' if res.get('unmapped') else ''}")


def main():
    p = argparse.ArgumentParser(description="Send Tally vouchers to Budget Planner.")
    p.add_argument("--app", required=True, help="Budget Planner address, e.g. https://budget.example.com")
    p.add_argument("--key", default=os.getenv("BUDGET_PLANNER_KEY", ""), help="integration key from Actuals > Tally")
    p.add_argument("--company", default="", help="Tally company name (leave out to use the open company)")
    p.add_argument("--tally-host", default="localhost")
    p.add_argument("--tally-port", default=9000, type=int)
    p.add_argument("--date-from", default="", help="YYYY-MM-DD (default: start of this financial year)")
    p.add_argument("--date-to", default="", help="YYYY-MM-DD (default: today)")
    p.add_argument("--every", default=0, type=int, help="repeat every N minutes (0 = run once)")
    a = p.parse_args()
    if not a.key:
        sys.exit("Give the integration key with --key or BUDGET_PLANNER_KEY.")
    while True:
        try:
            run_once(a)
        except urllib.error.HTTPError as e:
            print(f"Budget Planner refused: {e.code} {e.read().decode('utf-8', 'replace')[:300]}", file=sys.stderr)
        except urllib.error.URLError as e:
            print(f"Could not connect: {e.reason}. Is Tally open, and is the app address right?", file=sys.stderr)
        except ET.ParseError as e:
            print(f"Tally's answer could not be read: {e}", file=sys.stderr)
        if not a.every:
            break
        time.sleep(a.every * 60)


if __name__ == "__main__":
    main()
