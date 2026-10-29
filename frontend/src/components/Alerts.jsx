import { api } from '../lib'
import { useUi } from '../ui'
import { Badge } from './common'

const TONE = { high: ['bad', 'Act now'], medium: ['warn', 'Soon'], low: ['', 'For information'] }
const TAB_NAME = { tds: 'TDS', compare: 'Budget vs actual', actuals: 'Actuals' }

export default function Alerts({ data, reload, goTo }) {
  const { toast } = useUi()
  if (!data) return <div className="loading">Loading…</div>
  const dismiss = async (a) => { try { await api('/api/alerts/dismiss', { method: 'POST', body: { key: a.key } }); reload() } catch (e) { toast(e.message) } }
  const restore = async () => { await api('/api/alerts/restore', { method: 'POST' }); reload(); toast('Dismissed alerts are back') }
  const groups = ['TDS', 'Budget', 'Tally'].map((g) => [g, data.items.filter((a) => a.area === g)]).filter(([, l]) => l.length)
  return (
    <div className="cards">
      <div className="card">
        <div className="cardhead"><div><h2>Alerts</h2>
          <p className="sub">Worked out from the latest data each time: TDS short-deducted, missing PANs, payees near a threshold, deposits and quarterly statements due, spending over budget, income behind budget, and Tally ledgers waiting to be mapped. A dismissed alert comes back if the situation changes.</p></div>
          <button className="btn ghost" onClick={restore}>Show dismissed alerts</button></div>
        {!data.items.length && <div className="empty">Nothing needs attention.</div>}
        {groups.map(([g, list]) => (
          <section key={g}><h3>{g}</h3>
            <ul className="alerts">{list.map((a) => (
              <li key={a.key} className={`al ${a.severity}`}>
                <div><Badge tone={TONE[a.severity][0]}>{TONE[a.severity][1]}</Badge> <b>{a.title}</b><p>{a.detail}</p></div>
                <div className="tools">{goTo && <button className="btn sm" onClick={() => goTo(a.tab)}>Open {TAB_NAME[a.tab]}</button>}<button className="btn ghost sm" onClick={() => dismiss(a)}>Dismiss</button></div>
              </li>))}</ul>
          </section>))}
      </div>
    </div>
  )
}
