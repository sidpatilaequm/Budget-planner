"""Talking to Tally Prime / Tally.ERP 9 through its XML-over-HTTP interface.

Tally answers XML requests on the PC where it runs (Help > Settings > Connectivity: "TallyPrime acts as
Server", port 9000 by default). Two ways to bring data in:

1. Bridge (recommended when this app is hosted on the internet): tools/tally_bridge.py runs on the
   Tally PC, asks Tally for vouchers and posts them to /api/tally/push with an integration key.
2. Direct pull: when this server can reach the Tally PC (same network or VPN), "Sync now" asks Tally
   directly using the host and port saved in the Tally settings.
"""
import re
import urllib.request
import xml.etree.ElementTree as ET

_BAD = re.compile(r"&#(?:[0-8]|1[0-9]|2[0-9]|3[01]);|[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _esc(s: str) -> str:
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def voucher_request(company: str, date_from: str, date_to: str) -> str:
    """Asks for every voucher in the period with its ledger entries. Dates YYYY-MM-DD."""
    f, t = date_from.replace("-", ""), date_to.replace("-", "")
    co = f"<SVCURRENTCOMPANY>{_esc(company)}</SVCURRENTCOMPANY>" if company else ""
    return f"""<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>BudgetPlannerVouchers</ID></HEADER>
<BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT><SVFROMDATE>{f}</SVFROMDATE><SVTODATE>{t}</SVTODATE>{co}</STATICVARIABLES>
<TDL><TDLMESSAGE><COLLECTION NAME="BudgetPlannerVouchers" ISMODIFY="No"><TYPE>Voucher</TYPE>
<FETCH>GUID, DATE, VOUCHERTYPENAME, VOUCHERNUMBER, PARTYLEDGERNAME, NARRATION, ISCANCELLED, ISOPTIONAL, ALLLEDGERENTRIES.LIST, LEDGERENTRIES.LIST</FETCH>
<FILTER>BPNotCancelled</FILTER></COLLECTION>
<SYSTEM TYPE="Formulae" NAME="BPNotCancelled">NOT $IsCancelled AND NOT $IsOptional</SYSTEM></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>"""


def ledger_request(company: str) -> str:
    co = f"<SVCURRENTCOMPANY>{_esc(company)}</SVCURRENTCOMPANY>" if company else ""
    return f"""<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>BudgetPlannerLedgers</ID></HEADER>
<BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>{co}</STATICVARIABLES>
<TDL><TDLMESSAGE><COLLECTION NAME="BudgetPlannerLedgers" ISMODIFY="No"><TYPE>Ledger</TYPE><FETCH>NAME, PARENT</FETCH></COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>"""


def _root(xml_bytes: bytes | str) -> ET.Element:
    text = xml_bytes.decode("utf-8", "replace") if isinstance(xml_bytes, bytes) else xml_bytes
    text = _BAD.sub("", text)
    try:
        return ET.fromstring(text)
    except ET.ParseError as e:
        raise ValueError(f"Tally's answer could not be read: {e}")


def _t(el: ET.Element, tag: str) -> str:
    x = el.find(tag)
    return (x.text or "").strip() if x is not None and x.text else ""


def _num(s: str) -> float:
    s = (s or "").replace(",", "").strip()
    m = re.match(r"^-?\d+(\.\d+)?", s)            # amounts can carry a currency or "Dr/Cr" suffix
    return float(m.group(0)) if m else 0.0


def parse_vouchers(xml_bytes) -> list[dict]:
    """Vouchers from a Tally answer. Amounts keep Tally's sign (negative = debit)."""
    out = []
    for v in _root(xml_bytes).iter("VOUCHER"):
        if _t(v, "ISCANCELLED").lower() == "yes" or _t(v, "ISOPTIONAL").lower() == "yes":
            continue
        entries = []
        for tag in ("ALLLEDGERENTRIES.LIST", "LEDGERENTRIES.LIST"):
            for le in v.findall(tag):
                name = _t(le, "LEDGERNAME")
                if name:
                    entries.append({"ledger": name, "amount": _num(_t(le, "AMOUNT"))})
        out.append({"guid": _t(v, "GUID") or v.get("REMOTEID") or "", "date": _t(v, "DATE"),
                    "type": _t(v, "VOUCHERTYPENAME") or v.get("VCHTYPE") or "", "number": _t(v, "VOUCHERNUMBER"),
                    "party": _t(v, "PARTYLEDGERNAME"), "narration": _t(v, "NARRATION"), "entries": entries})
    return out


def parse_ledgers(xml_bytes) -> list[dict]:
    out = []
    for le in _root(xml_bytes).iter("LEDGER"):
        name = le.get("NAME") or _t(le, "NAME")
        if name:
            out.append({"name": name, "parent": _t(le, "PARENT")})
    return out


def post(host: str, port: int, body: str, timeout: int = 60) -> bytes:
    if not re.match(r"^[A-Za-z0-9.\-]+$", host or ""):
        raise ValueError("Enter Tally's host name or IP address.")
    req = urllib.request.Request(f"http://{host}:{int(port)}", data=body.encode("utf-8"),
                                 headers={"Content-Type": "text/xml; charset=utf-8"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 (host is configured by an administrator)
        return r.read()
