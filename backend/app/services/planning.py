"""Projects next year's budget from a base year.

Rules
- Overall % for expenses and for income; a head % overrides the overall; a line % overrides the head.
- Each line keeps its monthly pattern (every month is scaled by the same factor).
- A fixed (locked) expense head is held at base × (1 + head %). In automatic mode, lines without their own %
  absorb the difference; in manual mode nothing moves and the head must not end above its fixed amount.
- A fixed expense total is held at base × (1 + overall %). In automatic mode, heads that are neither fixed nor
  given their own % absorb the difference.
- Income lines with a quantity and a rate: the student % changes the quantity and the income % the rate.
"""
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..models import FiscalYear
from .budget import line_total, months, section_heads, spread


class PlanRequest(BaseModel):
    from_year_id: int
    exp: float | None = None
    inc: float | None = None
    qty: float | None = None
    head: dict[str, float] = Field(default_factory=dict)   # head id -> %
    item: dict[str, float] = Field(default_factory=dict)   # line id -> %
    lock: dict[str, bool] = Field(default_factory=dict)    # expense head id -> fixed
    lock_total: bool = False
    mode: str = "auto"                                      # auto | manual
    carry: bool = True
    replace: bool = False


def expense_plan(src: FiscalYear, req: PlanRequest) -> dict:
    g = req.exp or 0.0
    auto = req.mode != "manual"
    heads = []
    for hd in section_heads(src, "expense"):
        hv = req.head.get(str(hd.id))
        hp = hv if hv is not None else g
        locked = bool(req.lock.get(str(hd.id)))
        lines = []
        for ln in hd.lines:
            lv = req.item.get(str(ln.id))
            lines.append({"ln": ln, "b": line_total(ln), "over": lv is not None,
                          "f": 1 + (lv if lv is not None else hp) / 100})
        B = sum(l["b"] for l in lines)
        T = B * (1 + hp / 100)
        if locked and auto:
            fixed = sum(l["b"] * l["f"] for l in lines if l["over"])
            free = [l for l in lines if not l["over"] and l["b"]]
            FB = sum(l["b"] for l in free)
            if FB > 0:
                f = max(0.0, (T - fixed) / FB)
                for l in free:
                    l["f"] = f
        heads.append({"hd": hd, "lines": lines, "B": B, "T": T, "P": sum(l["b"] * l["f"] for l in lines),
                      "locked": locked, "has_pct": hv is not None})
    B = sum(h["B"] for h in heads)
    TT = B * (1 + g / 100)
    if req.lock_total and auto:
        free_heads = [h for h in heads if not h["locked"] and not h["has_pct"]]
        free_lines = [l for h in free_heads for l in h["lines"] if not l["over"] and l["b"]]
        F = sum(l["b"] * l["f"] for l in free_lines)
        fixed = sum(h["P"] for h in heads) - F
        if F > 0:
            k = max(0.0, (TT - fixed) / F)
            for l in free_lines:
                l["f"] *= k
            for h in free_heads:
                h["P"] = sum(l["b"] * l["f"] for l in h["lines"])
    return {"heads": heads, "B": B, "TT": TT, "P": sum(h["P"] for h in heads), "auto": auto}


def issues(ep: dict, req: PlanRequest) -> dict:
    over_heads = [h for h in ep["heads"] if h["locked"] and h["P"] > h["T"] + 0.5]
    total_over = ep["P"] - ep["TT"] if req.lock_total and ep["P"] > ep["TT"] + 0.5 else 0.0
    return {"heads": over_heads, "total": total_over, "count": len(over_heads) + (1 if total_over else 0)}


def project(src: FiscalYear, req: PlanRequest) -> tuple[dict, dict]:
    """Returns ({line_id: {"m": [...], "qty": q, "rate": r}}, expense_plan)."""
    ep = expense_plan(src, req)
    out = {}
    for h in ep["heads"]:
        for l in h["lines"]:
            ln = l["ln"]
            out[ln.id] = {"m": [float(round(v * l["f"])) for v in months(ln)],
                          "qty": float(ln.qty) if ln.qty is not None else None,
                          "rate": round(float(ln.rate) * l["f"], 2) if ln.rate is not None else None}

    def nudge(lines, target, current):
        if not lines:
            return
        big = max(lines, key=lambda ln: sum(out[ln.id]["m"]))
        d = round(target) - current
        if d:
            m = out[big.id]["m"]
            m[m.index(max(m))] += d

    if ep["auto"]:
        for h in ep["heads"]:
            if h["locked"] and abs(h["P"] - h["T"]) <= 0.5:
                free = [l["ln"] for l in h["lines"] if not l["over"] and l["b"]]
                nudge(free, h["T"], sum(sum(out[l["ln"].id]["m"]) for l in h["lines"]))
        if req.lock_total and abs(ep["P"] - ep["TT"]) <= 0.5:
            free = [l["ln"] for h in ep["heads"] if not h["locked"] and not h["has_pct"]
                    for l in h["lines"] if not l["over"] and l["b"]]
            nudge(free, ep["TT"], sum(sum(out[l["ln"].id]["m"]) for h in ep["heads"] for l in h["lines"]))

    qf = 1 + (req.qty or 0) / 100
    for hd in section_heads(src, "income"):
        hv = req.head.get(str(hd.id))
        for ln in hd.lines:
            lv = req.item.get(str(ln.id))
            pct = lv if lv is not None else hv if hv is not None else (req.inc or 0)
            f = 1 + pct / 100
            qr = ln.qty is not None and ln.rate is not None
            k = f * (qf if qr else 1)
            m = [float(round(v * k)) for v in months(ln)]
            qty = float(ln.qty) if ln.qty is not None else None
            rate = float(ln.rate) if ln.rate is not None else None
            if qr:
                qty = float(round(qty * qf))
                rate = round(rate * f, 2)
                m = spread(qty * rate, "keep", 0, m)
            elif rate is not None:
                rate = round(rate * f, 2)
            out[ln.id] = {"m": m, "qty": qty, "rate": rate}
    return out, ep


def _pct(a: float, b: float) -> float | None:
    return None if not b else round((a / b - 1) * 100, 1)


def preview(db: Session, src: FiscalYear, req: PlanRequest, target_exists: bool) -> dict:
    proj, ep = project(src, req)
    iss = issues(ep, req)
    ep_by_head = {h["hd"].id: h for h in ep["heads"]}
    sections = {}
    for section in ("expense", "income"):
        heads_out = []
        for hd in section_heads(src, section):
            lines_out = []
            for ln in hd.lines:
                b, p = line_total(ln), sum(proj[ln.id]["m"])
                lines_out.append({"id": ln.id, "name": ln.name, "base": b, "proj": p, "eff": _pct(p, b)})
            b = sum(l["base"] for l in lines_out)
            p = sum(l["proj"] for l in lines_out)
            row = {"id": hd.id, "name": hd.name, "base": b, "proj": p, "eff": _pct(p, b), "lines": lines_out}
            if section == "expense":
                e = ep_by_head[hd.id]
                row.update(locked=e["locked"], target=e["T"] if e["locked"] else None,
                           over=(e["P"] - e["T"]) if e["locked"] else None)
            heads_out.append(row)
        b = sum(h["base"] for h in heads_out)
        p = sum(h["proj"] for h in heads_out)
        sec = {"heads": heads_out, "base": b, "proj": p, "eff": _pct(p, b)}
        if section == "expense" and req.lock_total:
            sec.update(target=ep["TT"], over=ep["P"] - ep["TT"])
        sections[section] = sec
    inc, exp = sections["income"]["proj"], sections["expense"]["proj"]
    return {"from": {"id": src.id, "start": src.start_year}, "target": {"start": src.start_year + 1, "exists": target_exists},
            "sections": sections, "totals": {"income": inc, "expense": exp, "net": inc - exp},
            "issues": iss["count"]}
