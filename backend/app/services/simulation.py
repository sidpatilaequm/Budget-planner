"""Budget simulations: "what if" scenarios that never touch a budget until someone applies one.

A scenario starts from a year (its budget, actuals or a forecast), applies the same levers as next-year
planning (overall, head and line %, student numbers), then:
- adjustments: a % change or an amount, for a head or a line, over a range of months
  (an amount for a head is added as a new line, for example "New bus loan EMI");
- fee collection: the share of income actually collected in cash, for the cash-flow view;
- opening cash balance, for the month-by-month closing balance.
"""
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..models import FiscalYear
from . import actuals as A
from . import budget as B
from . import planning as P


class Adjustment(BaseModel):
    label: str = ""
    section: str = "expense"          # expense | income
    head_id: int | None = None        # a head of the base year
    line_id: int | None = None        # or one line of the base year
    kind: str = "pct"                 # pct | amount
    value: float = 0
    month_from: int = 0
    month_to: int = 11


class SimParams(BaseModel):
    from_year_id: int
    basis: str = "budget"
    upto: int | None = None
    exp: float | None = None
    inc: float | None = None
    qty: float | None = None
    head: dict[str, float] = Field(default_factory=dict)
    item: dict[str, float] = Field(default_factory=dict)
    adjustments: list[Adjustment] = Field(default_factory=list)
    collection: float = 100.0         # % of income collected in cash
    opening_cash: float = 0.0


def run(db: Session, src: FiscalYear, prm: SimParams) -> dict:
    req = P.PlanRequest(from_year_id=prm.from_year_id, exp=prm.exp, inc=prm.inc, qty=prm.qty, head=prm.head, item=prm.item,
                        basis=prm.basis, upto=prm.upto, mode="auto")
    base = A.base_months(db, src, prm.basis, prm.upto)
    proj, _ep = P.project(src, req, base)
    m_of = {ln.id: list(proj[ln.id]["m"]) for h in src.heads for ln in h.lines}
    head_of = {ln.id: h for h in src.heads for ln in h.lines}
    extra = []                                       # amount adjustments become lines of their own
    for a in prm.adjustments:
        lo, hi = max(0, min(a.month_from, 11)), max(0, min(a.month_to, 11))
        if hi < lo:
            lo, hi = hi, lo
        rng = range(lo, hi + 1)
        if a.kind == "pct":
            targets = [a.line_id] if a.line_id else [ln.id for h in src.heads if h.id == a.head_id for ln in h.lines] if a.head_id \
                else [ln.id for h in B.section_heads(src, a.section) for ln in h.lines]
            for lid in targets:
                if lid in m_of:
                    for i in rng:
                        m_of[lid][i] = round(m_of[lid][i] * (1 + a.value / 100))
        else:
            per = round(a.value / len(rng)) if rng else 0
            m = [per if i in rng else 0 for i in range(12)]
            if rng:
                m[hi] += round(a.value) - per * len(rng)
            hd = next((h for h in src.heads if h.id == a.head_id), None)
            if hd is None and a.line_id in head_of:
                hd = head_of[a.line_id]
            section = hd.section if hd else a.section
            extra.append({"section": section, "head_code": hd.code if hd else None, "head": hd.name if hd else "Other",
                          "name": a.label or ("Additional income" if section == "income" else "Additional expense"), "m": m})

    out = {"heads": {}, "months": {}}
    for section in ("income", "expense"):
        heads = []
        tot = [0.0] * 12
        for h in B.section_heads(src, section):
            bm = [0.0] * 12
            sm = [0.0] * 12
            for ln in h.lines:
                b = P._bm(ln, base)
                bm = [x + y for x, y in zip(bm, b)]
                sm = [x + y for x, y in zip(sm, m_of[ln.id])]
            for e in extra:
                if e["section"] == section and e["head_code"] == h.code:
                    sm = [x + y for x, y in zip(sm, e["m"])]
            heads.append({"id": h.id, "name": h.name, "base": round(sum(bm)), "sim": round(sum(sm)), "months": sm})
            tot = [x + y for x, y in zip(tot, sm)]
        for e in extra:
            if e["section"] == section and e["head_code"] is None:
                heads.append({"id": None, "name": e["name"], "base": 0, "sim": round(sum(e["m"])), "months": e["m"]})
                tot = [x + y for x, y in zip(tot, e["m"])]
        out["heads"][section] = heads
        out["months"][section] = tot
    inc, exp = out["months"]["income"], out["months"]["expense"]
    cash_in = [v * prm.collection / 100 for v in inc]
    closing, bal = [], prm.opening_cash
    for i in range(12):
        bal += cash_in[i] - exp[i]
        closing.append(round(bal))
    low = min(range(12), key=lambda i: closing[i])
    base_inc = sum(h["base"] for h in out["heads"]["income"])
    base_exp = sum(h["base"] for h in out["heads"]["expense"])
    return {"from": {"id": src.id, "start": src.start_year}, "basis": prm.basis,
            "heads": out["heads"], "income": [round(v) for v in inc], "expense": [round(v) for v in exp],
            "cash_in": [round(v) for v in cash_in], "closing": closing,
            "totals": {"income": round(sum(inc)), "expense": round(sum(exp)), "net": round(sum(inc) - sum(exp)),
                       "cash_net": round(sum(cash_in) - sum(exp)), "base_income": base_inc, "base_expense": base_exp,
                       "base_net": base_inc - base_exp, "lowest_cash": closing[low], "lowest_month": low,
                       "months_negative": sum(1 for v in closing if v < 0)},
            "_lines": m_of, "_extra": extra}
