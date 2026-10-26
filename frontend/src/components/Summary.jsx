import { api, compact, fyNice, instOf, INST, money, MONTH_FULL, MONTHS } from '../lib'
import { useLoad } from '../ui'

export default function Summary({ yearId }) {
  const [d, , , error] = useLoad(() => api(`/api/years/${yearId}/summary`), [yearId])
  if (error) return <div className="card"><div className="empty">{error}</div></div>
  if (!d) return <div className="loading">Loading…</div>
  const inc = d.income.months, exp = d.expense.months, net = inc.map((v, k) => v - exp[k])
  const prev = d.prev
  return (
    <div className="cards">
      <div className="card">
        <h2>Month by month</h2>
        <p className="sub">Bars show income and expenses for each month; the line shows the surplus or deficit.</p>
        <div className="legend">
          <span><i style={{ background: 'var(--income)' }} />Income</span>
          <span><i style={{ background: 'var(--expense)' }} />Expenses</span>
          <span><i style={{ background: 'var(--ink)', height: 3, verticalAlign: 3 }} />Surplus or deficit</span>
        </div>
        <div className="chart"><Chart inc={inc} exp={exp} net={net} label={fyNice(d.year.start)} /></div>
      </div>
      <div className="card">
        <h2>By installment</h2>
        <p className="sub">The three four-month periods used in your budget sheet.</p>
        <div className="scroll"><table className="list">
          <thead><tr><th>Period</th><th>Income</th><th>Expenses</th><th>Net</th></tr></thead>
          <tbody>
            {INST.map((s, j) => {
              const a = instOf(inc, j), b = instOf(exp, j)
              return <tr key={j}><td>{s.label} <span className="mut">({MONTHS[s.from]}–{MONTHS[s.to - 1]})</span></td><td>{money(a)}</td><td>{money(b)}</td><td className={a - b < 0 ? 'down' : ''}>{money(a - b)}</td></tr>
            })}
            <tr className="tt"><td>Year</td><td>{money(d.income.total)}</td><td>{money(d.expense.total)}</td><td className={d.income.total - d.expense.total < 0 ? 'down' : ''}>{money(d.income.total - d.expense.total)}</td></tr>
          </tbody>
        </table></div>
      </div>
      <HeadTable title="Expenses by head" sec={d.expense} prev={prev} cur={d.year} cls="sec-exp" expense />
      <HeadTable title="Income by head" sec={d.income} prev={prev} cur={d.year} cls="sec-inc" />
    </div>
  )
}

function HeadTable({ title, sec, prev, cur, cls, expense }) {
  const G = sec.total
  const rows = [...sec.heads].sort((a, b) => b.total - a.total)
  const change = (a, b) => {
    if (b == null) return <span className="mut">new</span>
    if (!b) return <span className="mut">{a ? 'new' : '–'}</span>
    const p = Math.round(((a - b) / b) * 1000) / 10
    const bad = expense ? p > 0 : p < 0
    return <span className={p === 0 ? 'mut' : bad ? 'down' : 'up'}>{p > 0 ? '+' : ''}{p}%</span>
  }
  return (
    <div className="card span6">
      <h2>{title}</h2>
      <p className="sub">{prev ? `Compared with FY ${fyNice(prev.start)}.` : 'Largest heads first.'}</p>
      <div className="scroll"><table className={`list ${cls}`}>
        <thead><tr><th>Head</th>{prev && <th>FY {fyNice(prev.start)}</th>}<th>FY {fyNice(cur.start)}</th>{prev && <th>Change</th>}<th>Share</th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}><td>{r.name}</td>
              {prev && <td>{r.prev != null ? money(r.prev) : <span className="mut">–</span>}</td>}
              <td>{money(r.total)}</td>
              {prev && <td>{change(r.total, r.prev)}</td>}
              <td><div className="share">{G ? `${Math.round((r.total / G) * 1000) / 10}%` : '–'}<div className="bar-s"><span style={{ width: `${G ? Math.max(0, (r.total / G) * 100) : 0}%` }} /></div></div></td>
            </tr>))}
          <tr className="tt"><td>Total</td>{prev && <td>{money(sec.prev_total)}</td>}<td>{money(G)}</td>{prev && <td>{change(G, sec.prev_total)}</td>}<td /></tr>
        </tbody>
      </table></div>
    </div>
  )
}

function Chart({ inc, exp, net, label }) {
  const W = 960, H = 300, L = 64, R = 12, T = 14, B = 30, pw = W - L - R, ph = H - T - B
  let mx = Math.max(1, ...inc, ...exp, ...net), mn = Math.min(0, ...net)
  if (mn < 0 && -mn < mx * 0.02) mn = 0
  const nice = (x) => { if (x <= 0) return 0; const p = 10 ** Math.floor(Math.log10(x)); const f = x / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p }
  const step = nice((mx - mn) / 4) || 1
  mx = Math.ceil(mx / step) * step; mn = Math.floor(mn / step) * step
  const Y = (v) => T + (ph * (mx - v)) / (mx - mn)
  const gw = pw / 12, bw = gw * 0.3
  const ticks = []
  for (let g = mn; g <= mx + 1e-6; g += step) ticks.push(g)
  const x = (k) => L + gw * k + gw / 2
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Monthly income and expenses for FY ${label}`}>
      {ticks.map((g) => <g key={g}>
        <line className={g === 0 ? 'zero' : 'gl'} x1={L} x2={W - R} y1={Y(g)} y2={Y(g)} />
        <text className="ax" x={L - 8} y={Y(g) + 4} textAnchor="end">{compact(g).replace('₹\u202F', '')}</text></g>)}
      {MONTHS.map((m, k) => <g key={m}>
        <rect className="bi" x={x(k) - bw - 1} y={Y(Math.max(0, inc[k]))} width={bw} height={Math.abs(Y(0) - Y(inc[k]))} rx="2"><title>{`${MONTH_FULL[k]} income ${money(inc[k])}`}</title></rect>
        <rect className="be" x={x(k) + 1} y={Y(Math.max(0, exp[k]))} width={bw} height={Math.abs(Y(0) - Y(exp[k]))} rx="2"><title>{`${MONTH_FULL[k]} expenses ${money(exp[k])}`}</title></rect>
        <text className="ax" x={x(k)} y={H - 10} textAnchor="middle">{m}</text></g>)}
      <polyline className="nl" points={net.map((n, k) => `${x(k)},${Y(n)}`).join(' ')} />
      {net.map((n, k) => <circle key={k} className="nd" cx={x(k)} cy={Y(n)} r="3.5"><title>{`${MONTH_FULL[k]} net ${money(n)}`}</title></circle>)}
    </svg>
  )
}
