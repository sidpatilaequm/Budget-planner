import { useEffect, useRef, useState } from 'react'
import { api, compact, fyNice, money, MONTH_FULL, MONTHS, parseNum, pctVal } from '../lib'
import { Chevron, useLoad, useUi } from '../ui'
import { Kpi } from './common'

const BASIS = { budget: 'Budget', actual: 'Actuals', forecast: 'Forecast: actuals so far, then budget' }
const blank = (yearId) => ({ from_year_id: yearId, basis: 'budget', exp: '', inc: '', qty: '', head: {}, adjustments: [], collection: '100', opening_cash: '' })

export default function Simulate({ years, yearId, can, onApplied }) {
  const { toast, confirm } = useUi()
  const [p, setP] = useState(blank(yearId))
  const [name, setName] = useState('')
  const [current, setCurrent] = useState(null)        // saved scenario being edited
  const [res, setRes] = useState(null)
  const [openHeads, setOpenHeads] = useState(false)
  const [pick, setPick] = useState([])
  const [cmp, setCmp] = useState(null)
  const [list, reloadList] = useLoad(() => api('/api/scenarios'), [])
  const [exp] = useLoad(() => api(`/api/years/${p.from_year_id}/sections/expense`), [p.from_year_id])
  const [inc] = useLoad(() => api(`/api/years/${p.from_year_id}/sections/income`), [p.from_year_id])
  const seq = useRef(0)

  const params = () => ({
    from_year_id: +p.from_year_id, basis: p.basis, exp: pctVal(p.exp), inc: pctVal(p.inc), qty: pctVal(p.qty),
    head: Object.fromEntries(Object.entries(p.head).map(([k, v]) => [k, pctVal(v)]).filter(([, v]) => v !== null)),
    adjustments: p.adjustments.map((a) => ({ ...a, head_id: a.head_id ? +a.head_id : null, value: a.kind === 'pct' ? pctVal(a.value) || 0 : parseNum(a.value), month_from: +a.month_from, month_to: +a.month_to })),
    collection: parseNum(p.collection || '100'), opening_cash: parseNum(p.opening_cash),
  })
  useEffect(() => {
    const n = ++seq.current
    const t = setTimeout(async () => {
      try { const r = await api('/api/simulate', { method: 'POST', body: params() }); if (n === seq.current) setRes(r) } catch (e) { toast(e.message) }
    }, 300)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p])

  const set = (patch) => setP((x) => ({ ...x, ...patch }))
  const setAdj = (i, patch) => setP((x) => ({ ...x, adjustments: x.adjustments.map((a, j) => (j === i ? { ...a, ...patch } : a)) }))
  const load = (s) => {
    const q = s.params
    setP({ from_year_id: q.from_year_id, basis: q.basis || 'budget', exp: q.exp ?? '', inc: q.inc ?? '', qty: q.qty ?? '', head: Object.fromEntries(Object.entries(q.head || {}).map(([k, v]) => [k, String(v)])),
      adjustments: (q.adjustments || []).map((a) => ({ ...a, value: String(a.value), head_id: a.head_id ? String(a.head_id) : '' })), collection: String(q.collection ?? 100), opening_cash: q.opening_cash ? String(q.opening_cash) : '' })
    setName(s.name); setCurrent(s)
  }
  const save = async (asNew) => {
    if (!name.trim()) { toast('Name the scenario first.'); return }
    try {
      const r = current && !asNew ? await api(`/api/scenarios/${current.id}`, { method: 'PUT', body: { name, params: params() } })
        : await api('/api/scenarios', { method: 'POST', body: { name, params: params() } })
      setCurrent(r); reloadList(); toast('Scenario saved')
    } catch (e) { toast(e.message) }
  }
  const remove = async (s) => { if (await confirm('Delete this scenario?', s.name, 'Delete')) { await api(`/api/scenarios/${s.id}`, { method: 'DELETE' }); if (current?.id === s.id) setCurrent(null); setPick(pick.filter((x) => x !== s.id)); reloadList() } }
  const compare = async () => { try { setCmp(await api('/api/scenarios/compare', { method: 'POST', body: { ids: pick } })) } catch (e) { toast(e.message) } }
  const apply = async (s) => {
    const src = years.find((y) => y.id === s.params.from_year_id)
    const tgt = src ? src.start + 1 : null
    const exists = years.some((y) => y.start === tgt)
    if (!await confirm(`Create FY ${fyNice(tgt)} from “${s.name}”?`, exists ? `FY ${fyNice(tgt)} already exists. Its amounts will be replaced by this scenario.` : 'The scenario’s amounts become the new year’s budget. Amount adjustments become new lines.', exists ? 'Replace year' : 'Create year')) return
    try { const r = await api(`/api/scenarios/${s.id}/apply`, { method: 'POST', body: { replace: exists } }); toast(`FY ${fyNice(r.year.start)} created`); onApplied(r.year.id) } catch (e) { toast(e.message) }
  }

  const allHeads = [...(exp?.heads || []).map((h) => ({ ...h, section: 'expense' })), ...(inc?.heads || []).map((h) => ({ ...h, section: 'income' }))]
  const t = res?.totals
  const delta = (a, b, good) => { const d = a - b; if (!Math.round(d)) return ''; return <span className={(good ? d > 0 : d < 0) ? 'up' : 'down'}>{d > 0 ? '+' : '−'}{compact(Math.abs(d))} vs base</span> }

  return (
    <div className="cards">
      <div className="card">
        <div className="cardhead"><div><h2>Budget simulation</h2>
          <p className="sub">Try “what if” changes without touching any budget: fee and student-number changes, cost increases, new loans or purchases in particular months, slower fee collection. See the surplus and the cash month by month, save scenarios, compare them, and turn the one you choose into next year’s budget.</p></div></div>
        <div className="planctl">
          <label className="field">Start from
            <select value={p.from_year_id} onChange={(e) => set({ from_year_id: +e.target.value, head: {}, adjustments: [] })}>{years.map((y) => <option key={y.id} value={y.id}>FY {fyNice(y.start)}</option>)}</select></label>
          <label className="field">Using
            <select value={p.basis} onChange={(e) => set({ basis: e.target.value })}>{Object.entries(BASIS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
          <Pct label="Change in expenses" value={p.exp} onChange={(v) => set({ exp: v })} />
          <Pct label="Change in fees and other income" value={p.inc} onChange={(v) => set({ inc: v })} />
          <Pct label="Change in student numbers" value={p.qty} onChange={(v) => set({ qty: v })} />
          <label className="field">Fees collected in cash<span className="pctwrap"><input className="inp" value={p.collection} inputMode="decimal" onChange={(e) => set({ collection: e.target.value })} /> %</span></label>
          <label className="field">Opening cash (₹)<input className="inp" value={p.opening_cash} inputMode="decimal" placeholder="0" onChange={(e) => set({ opening_cash: e.target.value })} /></label>
        </div>
        <h3><button className="tog" aria-expanded={openHeads} onClick={() => setOpenHeads(!openHeads)}><Chevron /></button> Change by head</h3>
        {openHeads && <div className="scroll"><table className="list"><thead><tr><th>Head</th><th>Change</th></tr></thead><tbody>
          {allHeads.map((h) => <tr key={h.id}><td>{h.name} <span className="mut">{h.section === 'income' ? 'income' : ''}</span></td>
            <td><input className="pi" value={p.head[h.id] ?? ''} placeholder={(h.section === 'income' ? p.inc : p.exp) || '0'} inputMode="decimal" aria-label={`${h.name} change percent`}
              onChange={(e) => setP((x) => { const m = { ...x.head }; if (e.target.value === '') delete m[h.id]; else m[h.id] = e.target.value; return { ...x, head: m } })} /> %</td></tr>)}
        </tbody></table></div>}
        <h3>Adjustments</h3>
        <p className="sub">For example: a new bus loan EMI of ₹12,00,000 from October to March; diesel up 10% from June; a fee rise of 5% only from the second installment.</p>
        {p.adjustments.map((a, i) => (
          <div className="adjrow" key={i}>
            <input value={a.label} placeholder="What it is" onChange={(e) => setAdj(i, { label: e.target.value })} aria-label="Adjustment name" />
            <select value={a.head_id} onChange={(e) => { const h = allHeads.find((x) => String(x.id) === e.target.value); setAdj(i, { head_id: e.target.value, section: h ? h.section : a.section }) }} aria-label="Head">
              <option value="">All {a.section === 'income' ? 'income' : 'expenses'}</option>
              <optgroup label="Expenses">{(exp?.heads || []).map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}</optgroup>
              <optgroup label="Income">{(inc?.heads || []).map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}</optgroup>
            </select>
            {!a.head_id && <select value={a.section} onChange={(e) => setAdj(i, { section: e.target.value })} aria-label="Section"><option value="expense">Expenses</option><option value="income">Income</option></select>}
            <select value={a.kind} onChange={(e) => setAdj(i, { kind: e.target.value })} aria-label="Kind"><option value="pct">Change by %</option><option value="amount">Add an amount (₹)</option></select>
            <input value={a.value} inputMode="decimal" placeholder={a.kind === 'pct' ? '%' : '₹ total'} onChange={(e) => setAdj(i, { value: e.target.value })} aria-label="Value" style={{ width: 110 }} />
            <select value={a.month_from} onChange={(e) => setAdj(i, { month_from: +e.target.value })} aria-label="From month">{MONTH_FULL.map((m, k) => <option key={k} value={k}>from {m}</option>)}</select>
            <select value={a.month_to} onChange={(e) => setAdj(i, { month_to: +e.target.value })} aria-label="To month">{MONTH_FULL.map((m, k) => <option key={k} value={k}>to {m}</option>)}</select>
            <button className="btn ghost sm" onClick={() => setP((x) => ({ ...x, adjustments: x.adjustments.filter((_, j) => j !== i) }))}>Remove</button>
          </div>))}
        <button className="btn sm" onClick={() => setP((x) => ({ ...x, adjustments: [...x.adjustments, { label: '', section: 'expense', head_id: '', kind: 'amount', value: '', month_from: 0, month_to: 11 }] }))}>Add adjustment</button>
      </div>

      {res && <>
        <div className="kpis">
          <Kpi label="Income" value={compact(t.income)} sub={delta(t.income, t.base_income, true)} />
          <Kpi label="Expenses" value={compact(t.expense)} sub={delta(t.expense, t.base_expense, false)} />
          <Kpi label={t.net < 0 ? 'Deficit' : 'Surplus'} value={compact(t.net)} tone={t.net < 0 ? 'bad' : 'good'} sub={delta(t.net, t.base_net, true)} />
          <Kpi label="Lowest cash balance" value={compact(t.lowest_cash)} tone={t.lowest_cash < 0 ? 'bad' : ''} sub={`end of ${MONTH_FULL[t.lowest_month]}${t.months_negative ? `; negative in ${t.months_negative} month${t.months_negative > 1 ? 's' : ''}` : ''}`} />
        </div>
        <div className="card">
          <h2>Cash month by month</h2>
          <p className="sub">Fees collected ({p.collection || 100}% of income) against expenses, and the closing balance from an opening balance of {money(parseNum(p.opening_cash))}.</p>
          <div className="legend"><span><i style={{ background: 'var(--income)' }} />Cash in</span><span><i style={{ background: 'var(--expense)' }} />Expenses</span><span><i style={{ background: 'var(--ink)', height: 3, verticalAlign: 3 }} />Closing cash</span></div>
          <div className="chart"><CashChart inc={res.cash_in} exp={res.expense} bal={res.closing} /></div>
          <div className="scroll"><table className="list compact"><thead><tr><th />{MONTHS.map((m) => <th key={m}>{m}</th>)}</tr></thead><tbody>
            <tr><td>Cash in</td>{res.cash_in.map((v, i) => <td key={i}>{compact(v)}</td>)}</tr>
            <tr><td>Expenses</td>{res.expense.map((v, i) => <td key={i}>{compact(v)}</td>)}</tr>
            <tr className="tt"><td>Closing</td>{res.closing.map((v, i) => <td key={i} className={v < 0 ? 'down' : ''}>{compact(v)}</td>)}</tr>
          </tbody></table></div>
        </div>
        <div className="card"><h2>By head</h2><div className="scroll"><table className="list"><thead><tr><th>Head</th><th>Base</th><th>Scenario</th><th>Change</th></tr></thead><tbody>
          {['income', 'expense'].map((sec) => [
            <tr className="ph" key={sec}><td colSpan={4}>{sec === 'income' ? 'Income' : 'Expenses'}</td></tr>,
            ...res.heads[sec].map((h, i) => <tr key={`${sec}${i}`}><td>{h.name}</td><td>{money(h.base)}</td><td>{money(h.sim)}</td>
              <td className={Math.round(h.sim - h.base) ? ((sec === 'income') === (h.sim > h.base) ? 'up' : 'down') : 'mut'}>{Math.round(h.sim - h.base) ? `${h.sim > h.base ? '+' : '−'}${money(Math.abs(h.sim - h.base))}` : '–'}</td></tr>)])}
        </tbody></table></div></div>
      </>}

      <div className="card">
        <div className="cardhead"><div><h2>Saved scenarios</h2><p className="sub">Save this simulation to come back to it, compare up to four side by side, or create next year’s budget from one.</p></div>
          <div className="tools"><input value={name} placeholder="Scenario name" onChange={(e) => setName(e.target.value)} aria-label="Scenario name" />
            <button className="btn primary" onClick={() => save(false)}>{current ? 'Save changes' : 'Save'}</button>
            {current && <button className="btn" onClick={() => save(true)}>Save as new</button>}
            {current && <button className="btn ghost" onClick={() => { setCurrent(null); setName(''); setP(blank(yearId)) }}>New simulation</button>}</div></div>
        {list?.length ? <table className="list"><thead><tr><th>Compare</th><th>Scenario</th><th>Based on</th><th>Saved</th><th /></tr></thead><tbody>
          {list.map((s) => <tr key={s.id} className={current?.id === s.id ? 'sel' : ''}>
            <td><input type="checkbox" checked={pick.includes(s.id)} disabled={!pick.includes(s.id) && pick.length >= 4} onChange={(e) => setPick(e.target.checked ? [...pick, s.id] : pick.filter((x) => x !== s.id))} aria-label={`Compare ${s.name}`} /></td>
            <td><b>{s.name}</b></td><td className="mut">FY {fyNice(years.find((y) => y.id === s.params.from_year_id)?.start ?? 0)} {BASIS[s.params.basis || 'budget'].split(':')[0].toLowerCase()}</td>
            <td className="mut">{new Date(s.updated_at).toLocaleDateString()} · {s.created_by}</td>
            <td style={{ whiteSpace: 'nowrap' }}><button className="btn ghost sm" onClick={() => load(s)}>Open</button>
              {can('plan_year') && <button className="btn ghost sm" onClick={() => apply(s)}>Create next year from this</button>}
              <button className="btn ghost sm" onClick={() => remove(s)}>Delete</button></td></tr>)}
        </tbody></table> : <div className="empty">No saved scenarios yet.</div>}
        {pick.length >= 2 && <div className="tools" style={{ marginTop: 10 }}><button className="btn" onClick={compare}>Compare {pick.length} scenarios</button></div>}
        {cmp && <div className="scroll" style={{ marginTop: 12 }}><table className="list">
          <thead><tr><th />{cmp.map((c) => <th key={c.id}>{c.name}</th>)}</tr></thead>
          <tbody>
            {[['Income', 'income'], ['Expenses', 'expense'], ['Surplus or deficit', 'net'], ['Cash surplus after collection', 'cash_net'], ['Lowest cash balance', 'lowest_cash']].map(([l, k]) => (
              <tr key={k}><td>{l}</td>{cmp.map((c) => <td key={c.id} className={c.totals[k] < 0 ? 'down' : ''}>{money(c.totals[k])}</td>)}</tr>))}
            <tr><td>Months with negative cash</td>{cmp.map((c) => <td key={c.id}>{c.totals.months_negative || '–'}</td>)}</tr>
          </tbody></table>
          <div className="chart"><CompareChart series={cmp.map((c) => ({ name: c.name, v: c.closing }))} /></div>
        </div>}
      </div>
    </div>
  )
}

const Pct = ({ label, value, onChange }) => (
  <label className="field">{label}<span className="pctwrap"><input className="inp" value={value} placeholder="0" inputMode="decimal" onChange={(e) => onChange(e.target.value)} /> %</span></label>
)

function scale(vals, H, pad) {
  const max = Math.max(1, ...vals), min = Math.min(0, ...vals)
  return { y: (v) => pad + (H - 2 * pad) * (1 - (v - min) / (max - min || 1)), zero: pad + (H - 2 * pad) * (1 - (0 - min) / (max - min || 1)) }
}

function CashChart({ inc, exp, bal }) {
  const W = 760, H = 240, P = 22, n = 12, bw = (W - 2 * P) / n
  const s = scale([...inc, ...exp, ...bal], H, P)
  const pts = bal.map((v, i) => `${P + bw * i + bw / 2},${s.y(v)}`).join(' ')
  return (
    <svg viewBox={`0 0 ${W} ${H + 18}`} role="img" aria-label="Cash in, expenses and closing cash by month">
      <line x1={P} x2={W - P} y1={s.zero} y2={s.zero} stroke="var(--rule-strong)" />
      {inc.map((v, i) => <rect key={`i${i}`} x={P + bw * i + bw * 0.12} width={bw * 0.36} y={Math.min(s.y(v), s.zero)} height={Math.abs(s.zero - s.y(v))} fill="var(--income)" rx="2"><title>{`${MONTHS[i]} cash in ${money(v)}`}</title></rect>)}
      {exp.map((v, i) => <rect key={`e${i}`} x={P + bw * i + bw * 0.52} width={bw * 0.36} y={Math.min(s.y(v), s.zero)} height={Math.abs(s.zero - s.y(v))} fill="var(--expense)" rx="2"><title>{`${MONTHS[i]} expenses ${money(v)}`}</title></rect>)}
      <polyline points={pts} fill="none" stroke="var(--ink)" strokeWidth="2.5" />
      {bal.map((v, i) => <circle key={`b${i}`} cx={P + bw * i + bw / 2} cy={s.y(v)} r="3.5" fill={v < 0 ? 'var(--expense)' : 'var(--ink)'}><title>{`${MONTHS[i]} closing ${money(v)}`}</title></circle>)}
      {MONTHS.map((m, i) => <text key={m} x={P + bw * i + bw / 2} y={H + 12} textAnchor="middle" fontSize="9" fill="var(--muted)">{m}</text>)}
    </svg>
  )
}

const LINE_COLORS = ['var(--accent)', 'var(--income)', 'var(--expense)', 'var(--warn)']
function CompareChart({ series }) {
  const W = 760, H = 200, P = 22, bw = (W - 2 * P) / 12
  const s = scale(series.flatMap((x) => x.v), H, P)
  return (
    <svg viewBox={`0 0 ${W} ${H + 36}`} role="img" aria-label="Closing cash by month for each scenario">
      <line x1={P} x2={W - P} y1={s.zero} y2={s.zero} stroke="var(--rule-strong)" />
      {series.map((x, k) => <polyline key={k} points={x.v.map((v, i) => `${P + bw * i + bw / 2},${s.y(v)}`).join(' ')} fill="none" stroke={LINE_COLORS[k]} strokeWidth="2.5" />)}
      {MONTHS.map((m, i) => <text key={m} x={P + bw * i + bw / 2} y={H + 12} textAnchor="middle" fontSize="9" fill="var(--muted)">{m}</text>)}
      {series.map((x, k) => <text key={x.name} x={P + k * 180} y={H + 30} fontSize="12" fill={LINE_COLORS[k]}>● {x.name}</text>)}
    </svg>
  )
}
