import { useEffect, useState } from 'react'
import { api, fyNice, money, pctVal } from '../lib'
import { useUi } from '../ui'

export default function Limits({ yearId, onChanged }) {
  const { toast, confirm } = useUi()
  const [d, setD] = useState(null)
  const [drafts, setDrafts] = useState({})
  const [allPct, setAllPct] = useState('')

  useEffect(() => { api(`/api/years/${yearId}/limits`).then(setD).catch((e) => toast(e.message)) }, [yearId, toast])

  const put = async (body) => {
    try { setD(await api(`/api/years/${yearId}/limits`, { method: 'PUT', body })); onChanged() } catch (e) { toast(e.message) }
  }
  if (!d) return <div className="loading">Loading…</div>

  const pv = d.prev
  const opts = (
    <>
      <option value="none">No limit</option>
      <option value="amount">Fixed amount</option>
      <option value="growth" disabled={!pv}>Growth over FY {fyNice(d.year.start - 1)}</option>
    </>
  )
  const status = (l, a) => (l == null ? <span className="mut">–</span>
    : a > l + 0.5 ? <span className="down">{money(a - l)} over</span> : <span className="up">{money(l - a)} left</span>)
  const commitValue = (key, mode, apply) => {
    const raw = drafts[key]
    if (raw === undefined) return
    setDrafts((x) => { const n = { ...x }; delete n[key]; return n })
    const v = pctVal(String(raw).replace(/[,₹\s]/g, ''))
    apply({ mode, value: v ?? 0 })
  }
  const valueInput = (key, l, apply, cls = 'pi wide') => (l.mode === 'none' ? <span className="mut">–</span> : (
    <span className="pctwrap" style={{ justifyContent: 'flex-end' }}>{l.mode === 'amount' && '₹'}
      <input className={cls} inputMode="decimal" aria-label="Limit value" value={drafts[key] ?? (l.value ?? '')}
        onChange={(e) => setDrafts({ ...drafts, [key]: e.target.value })}
        onBlur={() => commitValue(key, l.mode, apply)} onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()} />
      {l.mode === 'growth' && '%'}</span>))

  const T = d.total
  const sumHL = d.heads.reduce((s, h) => s + (h.limit ?? 0), 0)
  const nHL = d.heads.filter((h) => h.limit != null).length
  const over = T.limit != null && T.budgeted > T.limit + 0.5

  const headMode = (h, mode) => put({ heads: { [h.id]: { mode, value: mode === 'amount' ? Math.round(h.budgeted) : mode === 'growth' ? 0 : null } } })
  const allGrowth = () => {
    const g = pctVal(allPct)
    if (g == null) return toast('Enter a growth percent first')
    put({ heads: Object.fromEntries(d.heads.filter((h) => h.base != null).map((h) => [h.id, { mode: 'growth', value: g }])) })
  }
  const allCurrent = () => put({ heads: Object.fromEntries(d.heads.map((h) => [h.id, { mode: 'amount', value: Math.round(h.budgeted) }])) })
  const clearAll = async () => {
    if (!await confirm('Clear all head limits?', 'The overall limit stays as it is.', 'Clear limits')) return
    put({ heads: Object.fromEntries(d.heads.map((h) => [h.id, { mode: 'none', value: null }])) })
  }

  return (
    <div className="cards">
      <div className="card">
        <h2>Expense limits for FY {fyNice(d.year.start)}</h2>
        <p className="sub">A limit caps how much can be budgeted. When an entry in the Expenses tab would take a head, or the total, over its limit, it is blocked or flagged. Lowering amounts is always allowed.</p>
        <div className="planctl">
          <label className="field">Overall expense limit
            <select value={T.mode} onChange={(e) => {
              const mode = e.target.value
              put({ total: { mode, value: mode === 'amount' ? Math.round(Math.max(T.limit ?? 0, T.budgeted)) : mode === 'growth' ? 0 : null } })
            }}>{opts}</select></label>
          <label className="field">{T.mode === 'growth' ? 'Growth' : 'Amount'}
            {T.mode === 'none' ? <span className="mut" style={{ padding: '7px 0' }}>Not set</span>
              : valueInput('total', T, (l) => put({ total: l }), 'inp')}</label>
          <label className="field">When an entry goes over a limit
            <select value={d.rule} onChange={(e) => put({ rule: e.target.value })}>
              <option value="block">Block it</option>
              <option value="warn">Allow it, but show the overage</option>
            </select></label>
        </div>
        <div className="limsum">
          <div><span>Overall limit</span><b>{T.limit != null ? money(T.limit) : 'None'}</b></div>
          <div><span>Budgeted now</span><b>{money(T.budgeted)}</b></div>
          <div><span>{over ? 'Over' : 'Left'}</span><b className={over ? 'down' : ''}>{T.limit != null ? money(Math.abs(T.limit - T.budgeted)) : '–'}</b></div>
          {pv && <div><span>FY {fyNice(pv.start)} total</span><b>{money(T.base)}</b></div>}
        </div>
        {!pv && <p className="plan-note">Growth limits need FY {fyNice(d.year.start - 1)} in the planner. Use fixed amounts, or add that year first.</p>}
      </div>
      <div className="card">
        <div className="cardhead">
          <div><h2>Limits by head</h2><p className="sub">Set a limit on any head. Heads without a limit are bounded only by the overall limit.</p></div>
          <div className="tools">
            {pv && <><span className="pctwrap"><input className="inp" value={allPct} placeholder="0" inputMode="decimal" aria-label="Growth percent for all heads" onChange={(e) => setAllPct(e.target.value)} />%</span>
              <button className="btn sm" onClick={allGrowth}>Set every head to this growth</button></>}
            <button className="btn sm" onClick={allCurrent}>Fix every head at its current amount</button>
            <button className="btn ghost sm danger" onClick={clearAll}>Clear head limits</button>
          </div>
        </div>
        <div className="scroll"><table className="list">
          <thead><tr><th>Head</th><th>{pv ? `FY ${fyNice(pv.start)}` : 'Last year'}</th><th>Limit type</th><th>Value</th><th>Limit</th><th>Budgeted</th><th>Status</th></tr></thead>
          <tbody>
            {d.heads.map((h) => (
              <tr key={h.id}>
                <td>{h.name}</td>
                <td>{h.base != null ? money(h.base) : <span className="mut">–</span>}</td>
                <td><select value={h.mode} aria-label={`${h.name} limit type`} onChange={(e) => headMode(h, e.target.value)}>{opts}</select></td>
                <td>{valueInput(`h${h.id}`, h, (l) => put({ heads: { [h.id]: l } }))}</td>
                <td>{h.limit != null ? money(h.limit) : <span className="mut">–</span>}</td>
                <td>{money(h.budgeted)}</td>
                <td>{status(h.limit, h.budgeted)}</td>
              </tr>))}
            <tr className="tt"><td>Total</td><td>{pv ? money(T.base) : ''}</td><td /><td /><td>{nHL ? money(sumHL) : <span className="mut">–</span>}</td><td>{money(T.budgeted)}</td><td>{status(T.limit, T.budgeted)}</td></tr>
          </tbody>
        </table></div>
        {T.limit != null && nHL > 0 && sumHL > T.limit + 0.5 &&
          <p className="warnbox">Head limits add up to {money(sumHL)}, which is {money(sumHL - T.limit)} more than the overall limit. Users will hit the overall limit before every head reaches its own.</p>}
      </div>
    </div>
  )
}
