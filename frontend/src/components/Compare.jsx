import { useState } from 'react'
import { api, compact, fyNice, money, MONTH_FULL, MONTHS, sum } from '../lib'
import { Chevron, useLoad } from '../ui'
import { Kpi, SubTabs } from './common'

export default function Compare({ year, can }) {
  const sections = [can('view_expense') && ['expense', 'Expenses'], can('view_income') && ['income', 'Income']].filter(Boolean)
  const [section, setSection] = useState(sections[0]?.[0])
  const [d, , , error] = useLoad(() => api(`/api/years/${year.id}/compare/${section}`), [year.id, section])
  const [open, setOpen] = useState({})
  const [view, setView] = useState('ytd')
  if (error) return <div className="card"><div className="empty">{error}</div></div>
  if (!d) return <div className="loading">Loading…</div>
  const ex = section === 'expense'
  const upto = d.upto
  const ytd = (m) => (upto < 0 ? 0 : sum(m.slice(0, upto + 1)))
  const bY = ytd(d.budget), aY = ytd(d.actual), bFull = sum(d.budget), aFull = sum(d.actual)
  const forecast = aY + sum(d.budget.slice(upto + 1))
  const varCell = (b, a) => {
    const v = a - b
    if (!Math.round(v)) return <td className="mut">–</td>
    const bad = ex ? v > 0 : v < 0
    const pct = b ? ` (${v > 0 ? '+' : '−'}${Math.abs(Math.round((v / b) * 100))}%)` : ''
    return <td className={bad ? 'down' : 'up'}>{v > 0 ? '+' : '−'}{money(Math.abs(v))}<span className="mut">{pct}</span></td>
  }
  const used = (b, a) => {
    const p = b ? Math.min(150, Math.round((a / b) * 100)) : a ? 150 : 0
    return <span className="meter" title={`${p}% of the year’s budget`}><i style={{ width: `${Math.min(100, p)}%` }} className={p > 100 ? 'over' : ''} /></span>
  }
  return (
    <div className="cards">
      <SubTabs tabs={sections} value={section} onChange={setSection} />
      <div className="kpis">
        <Kpi label={upto < 0 ? 'No actuals yet' : `Budget to ${MONTH_FULL[upto]}`} value={compact(bY)} />
        <Kpi label={`Actual to ${upto < 0 ? '—' : MONTH_FULL[upto]}`} value={compact(aY)} tone={ex ? (aY > bY ? 'bad' : 'good') : (aY < bY ? 'bad' : 'good')}
          sub={bY ? `${Math.round((aY / bY) * 100)}% of budget so far` : ''} />
        <Kpi label="Full-year budget" value={compact(bFull)} sub={`${bFull ? Math.round((aFull / bFull) * 100) : 0}% ${ex ? 'spent' : 'received'}`} />
        <Kpi label="Forecast for the year" value={compact(forecast)} sub="actuals so far, budget for the rest" />
      </div>
      <div className="card">
        <div className="cardhead"><div><h2>{ex ? 'Expenses' : 'Income'}: budget against actual, FY {fyNice(year.start)}</h2>
          <p className="sub">{ex ? 'Spending above budget shows in red.' : 'Income below budget shows in red.'} Actuals come from Tally, the entry screen and Excel imports.</p></div>
          <div className="tools"><select value={view} onChange={(e) => setView(e.target.value)} aria-label="View">
            <option value="ytd">Year to date and full year</option><option value="months">Month by month</option></select></div></div>
        <div className="scroll">{view === 'ytd' ? (
          <table className="list">
            <thead><tr><th>Head</th><th>Budget to date</th><th>Actual to date</th><th>Difference</th><th>Year budget</th><th>Used</th><th>Forecast</th></tr></thead>
            <tbody>
              {d.heads.map((h) => [
                <tr className="ph" key={h.id}>
                  <td><button className="tog" aria-expanded={!!open[h.id]} aria-label="Show lines" onClick={() => setOpen({ ...open, [h.id]: !open[h.id] })}><Chevron /></button>{h.name}</td>
                  <td>{money(ytd(h.budget))}</td><td>{money(ytd(h.actual))}</td>{varCell(ytd(h.budget), ytd(h.actual))}
                  <td>{money(sum(h.budget))}</td><td>{used(sum(h.budget), sum(h.actual))}</td><td>{money(ytd(h.actual) + sum(h.budget.slice(upto + 1)))}</td>
                </tr>,
                ...(open[h.id] ? h.lines.map((l) => (
                  <tr className="pi-row" key={`l${l.id}`}><td>{l.name}</td><td>{money(ytd(l.budget))}</td><td>{money(ytd(l.actual))}</td>{varCell(ytd(l.budget), ytd(l.actual))}
                    <td>{money(sum(l.budget))}</td><td>{used(sum(l.budget), sum(l.actual))}</td><td>{money(ytd(l.actual) + sum(l.budget.slice(upto + 1)))}</td></tr>)) : []),
              ])}
              {d.other.length > 0 && <tr><td className="mut" colSpan={7}>{d.other.length} line{d.other.length > 1 ? 's' : ''} with actuals are not in this year’s budget ({money(sum(d.other.map((o) => sum(o.actual))))}). They count in the totals.</td></tr>}
              <tr className="tt"><td>Total</td><td>{money(bY)}</td><td>{money(aY)}</td>{varCell(bY, aY)}<td>{money(bFull)}</td><td>{used(bFull, aFull)}</td><td>{money(forecast)}</td></tr>
            </tbody>
          </table>
        ) : (
          <table className="list compact">
            <thead><tr><th>Head</th>{MONTHS.map((m) => <th key={m}>{m}</th>)}<th>Year</th></tr></thead>
            <tbody>
              {d.heads.map((h) => (
                <tr key={h.id}><td>{h.name}</td>
                  {h.actual.map((a, i) => { const b = h.budget[i]; const bad = ex ? a > b * 1.0001 : a < b * 0.9999; return <td key={i} className={i <= upto && (a || b) ? (bad ? 'down' : 'up') : 'mut'} title={`Budget ${money(b)}`}>{i <= upto ? compact(a) : <span className="mut">{compact(b)}</span>}</td> })}
                  <td>{compact(sum(h.actual))}</td></tr>))}
              <tr className="tt"><td>Total</td>{d.actual.map((a, i) => <td key={i}>{i <= upto ? compact(a) : <span className="mut">{compact(d.budget[i])}</span>}</td>)}<td>{compact(aFull)}</td></tr>
            </tbody>
          </table>
        )}</div>
        {view === 'months' && <p className="mut">Months with actuals show the actual amount, coloured against the budget (hover to see it). Later months show the budget in grey.</p>}
      </div>
    </div>
  )
}
