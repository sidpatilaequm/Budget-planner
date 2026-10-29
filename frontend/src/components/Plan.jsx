import { useEffect, useRef, useState } from 'react'
import { api, compact, fyNice, money, pctText, pctVal } from '../lib'
import { Chevron, useUi } from '../ui'

export default function Plan({ years, yearId, can, onCreated }) {
  const BASIS = { budget: 'its budget', actual: 'its actuals', forecast: 'a forecast: actuals so far, budget for the rest' }
  const { toast, confirm } = useUi()
  const [p, setP] = useState({ from: yearId, basis: 'budget', exp: '', inc: '', qty: '', head: {}, item: {}, lock: {}, lockTotal: false, mode: 'auto', carry: true })
  const [open, setOpen] = useState({})
  const [pv, setPv] = useState(null)
  const [busy, setBusy] = useState(false)
  const seq = useRef(0)

  const request = (extra = {}) => {
    const nums = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, pctVal(v)]).filter(([, v]) => v !== null))
    return {
      from_year_id: +p.from, exp: pctVal(p.exp), inc: pctVal(p.inc), qty: pctVal(p.qty),
      head: nums(p.head), item: nums(p.item), lock: p.lock, lock_total: p.lockTotal, mode: p.mode,
      carry: p.carry && can('manage_limits'), basis: p.basis, ...extra,
    }
  }

  useEffect(() => {
    const n = ++seq.current
    const t = setTimeout(async () => {
      try {
        const r = await api('/api/plan/preview', { method: 'POST', body: request() })
        if (n === seq.current) setPv(r)
      } catch (e) { toast(e.message) }
    }, 250)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p])

  const set = (patch) => setP((x) => ({ ...x, ...patch }))
  const setMap = (key, id, val) => setP((x) => {
    const m = { ...x[key] }
    if (val === '' || val === false) delete m[id]; else m[id] = val
    return { ...x, [key]: m }
  })

  const create = async () => {
    setBusy(true)
    try {
      let r
      try { r = await api('/api/plan/create', { method: 'POST', body: request() }) } catch (e) {
        if (e.status !== 409 || !pv?.target.exists) throw e
        if (!await confirm(`Replace FY ${fyNice(pv.target.start)}?`, `FY ${fyNice(pv.target.start)} already exists. Replacing it overwrites every amount in that year with this projection.`, 'Replace year')) return
        r = await api('/api/plan/create', { method: 'POST', body: request({ replace: true }) })
      }
      toast(`FY ${fyNice(r.year.start)} budget created${r.limits ? ` with ${r.limits} limit${r.limits === 1 ? '' : 's'}` : ''}`)
      onCreated(r.year.id)
    } catch (e) { toast(e.message) } finally { setBusy(false) }
  }

  if (!pv) return <div className="loading">Working out the projection…</div>
  const src = years.find((y) => y.id === +p.from)
  const tgt = pv.target.start

  const diff = (a, b, expense) => {
    const d = a - b
    if (!Math.round(d)) return <span className="mut">–</span>
    const good = expense ? d < 0 : d > 0
    return <span className={good ? 'up' : 'down'}>{d > 0 ? '+' : '−'}{money(Math.abs(d))}</span>
  }
  const status = (target, over) => {
    if (target == null) return null
    if (over > 0.5) return <span className="down">{money(over)} over the fixed {money(target)}. Reduce a line.</span>
    if (-over > 0.5) return <span className="mut">Fixed at {money(target)}, {money(-over)} unused</span>
    return <span className="mut">Fixed at {money(target)}</span>
  }

  const table = (section) => {
    const ex = section === 'expense'
    const sec = pv.sections[section]
    const base = (ex ? p.exp : p.inc) || '0'
    return (
      <div className="scroll"><table className="list">
        <thead><tr><th>Head</th><th>FY {fyNice(src.start)}</th><th>Change</th>{ex && <th>Fixed</th>}<th>FY {fyNice(tgt)}</th><th>Difference</th><th>Effective change</th></tr></thead>
        <tbody>
          {sec.heads.map((h) => {
            const isOpen = !!open[h.id]
            const hv = p.head[h.id] ?? ''
            return [
              <tr className="ph" key={`h${h.id}`}>
                <td><button className="tog" aria-expanded={isOpen} aria-label="Show lines" onClick={() => setOpen({ ...open, [h.id]: !isOpen })}><Chevron /></button>{h.name}
                  {ex && h.locked && <div className="stat">{status(h.target, h.over)}</div>}</td>
                <td>{money(h.base)}</td>
                <td><input className="pi" value={hv} placeholder={base} inputMode="decimal" aria-label={`${h.name} change percent`} onChange={(e) => setMap('head', h.id, e.target.value)} /> %</td>
                {ex && <td className="fx"><input type="checkbox" checked={!!p.lock[h.id]} aria-label={`Fix ${h.name} at its change`} onChange={(e) => setMap('lock', h.id, e.target.checked)} /></td>}
                <td>{money(h.proj)}</td><td>{diff(h.proj, h.base, ex)}</td><td>{pctText(h.eff)}</td>
              </tr>,
              ...(isOpen ? h.lines.map((l) => (
                <tr className="pi-row" key={`l${l.id}`}>
                  <td>{l.name}</td><td>{money(l.base)}</td>
                  <td><input className="pi" value={p.item[l.id] ?? ''} placeholder={hv !== '' ? hv : base} inputMode="decimal" aria-label={`${l.name} change percent`} onChange={(e) => setMap('item', l.id, e.target.value)} /> %</td>
                  {ex && <td />}
                  <td>{money(l.proj)}</td><td>{diff(l.proj, l.base, ex)}</td><td>{pctText(l.eff)}</td>
                </tr>)) : []),
            ]
          })}
          <tr className="tt">
            <td>Total {ex ? 'expenses' : 'income'}{ex && p.lockTotal && <div className="stat">{status(sec.target, sec.over)}</div>}</td>
            <td>{money(sec.base)}</td><td />{ex && <td />}<td>{money(sec.proj)}</td><td>{diff(sec.proj, sec.base, ex)}</td><td>{pctText(sec.eff)}</td>
          </tr>
        </tbody>
      </table></div>
    )
  }

  const t = pv.totals
  return (
    <>
      <div className="cards">
        <div className="card">
          <h2>Plan FY {fyNice(tgt)} from FY {fyNice(src.start)}</h2>
          <p className="sub">{p.basis !== 'budget' && <><b>Starting from {BASIS[p.basis]}</b> (from Tally and the actuals screen). </>}Set an overall change, then override any head or line. Every change rolls up to its head and to the total. Each line keeps its month-by-month pattern.</p>
          <div className="planctl">
            <label className="field">Base year
              <select value={p.from} onChange={(e) => set({ from: +e.target.value, head: {}, item: {}, lock: {} })}>
                {years.map((y) => <option key={y.id} value={y.id}>FY {fyNice(y.start)}</option>)}
              </select></label>
            {can('view_actuals') && <label className="field">Plan from
              <select value={p.basis} onChange={(e) => set({ basis: e.target.value })}>
                {Object.entries(BASIS).map(([k, l]) => <option key={k} value={k}>{l[0].toUpperCase() + l.slice(1)}</option>)}
              </select></label>}
            <Pct label="Change in expenses" value={p.exp} onChange={(v) => set({ exp: v })} />
            <Pct label="Change in fees and other income" value={p.inc} onChange={(v) => set({ inc: v })} />
            <Pct label="Change in student numbers" value={p.qty} onChange={(v) => set({ qty: v })} />
          </div>
          <div className="ctlrow">
            <h3>Fixed budgets for expenses</h3>
            <label className="chk"><input type="checkbox" checked={p.lockTotal} onChange={(e) => set({ lockTotal: e.target.checked })} /> Keep total expenses fixed at the overall change</label>
            <label className="field">When a line or head changes inside a fixed budget
              <select value={p.mode} onChange={(e) => set({ mode: e.target.value })}>
                <option value="auto">Adjust the others automatically</option>
                <option value="manual">Make me adjust the others myself</option>
              </select></label>
            {can('manage_limits') && <label className="chk"><input type="checkbox" checked={p.carry} onChange={(e) => set({ carry: e.target.checked })} /> Save fixed budgets as limits in FY {fyNice(tgt)}</label>}
          </div>
          <p className="plan-note">Tick <b>Fixed</b> on a head to hold it at its change. In automatic mode, lines you have not set yourself absorb the difference; with the total fixed, heads you have not set or fixed absorb it. In manual mode nothing moves for you, and the year can be created only when every fixed budget is within its amount. Use a minus sign to decrease, for example −5.</p>
        </div>
        <div className="card">
          <div className="cardhead"><div><h2>Expenses</h2><p className="sub">Leave a box empty to use the overall change.</p></div>
            <div className="tools">
              <button className="btn sm" onClick={() => set({ lock: Object.fromEntries(pv.sections.expense.heads.map((h) => [h.id, true])) })}>Fix all heads</button>
              <button className="btn ghost sm" onClick={() => set({ lock: {} })}>Unfix all</button>
            </div></div>
          {table('expense')}
        </div>
        <div className="card"><h2>Income</h2><p className="sub">Leave a box empty to use the overall change.</p>{table('income')}</div>
      </div>
      <div className="plansum">
        <div className="k"><span>Projected income</span><b>{compact(t.income)}</b></div>
        <div className="k"><span>Projected expenses</span><b>{compact(t.expense)}</b></div>
        <div className="k"><span>{t.net < 0 ? 'Projected deficit' : 'Projected surplus'}</span><b>{compact(t.net)}</b></div>
        <span className="spacer" />
        {pv.issues > 0 && <span className="stat" style={{ maxWidth: 340, fontSize: 12 }}><span className="down">
          {pv.issues === 1 ? 'One fixed budget is' : `${pv.issues} fixed budgets are`} over. Bring {pv.issues === 1 ? 'it' : 'them'} within the fixed amount to create the year.</span></span>}
        <button className="btn primary" disabled={busy || pv.issues > 0} onClick={create}>{pv.target.exists ? 'Replace' : 'Create'} FY {fyNice(tgt)} budget</button>
      </div>
    </>
  )
}

const Pct = ({ label, value, onChange }) => (
  <label className="field">{label}<span className="pctwrap"><input className="inp" value={value} placeholder="0" inputMode="decimal" onChange={(e) => onChange(e.target.value)} /> %</span></label>
)
