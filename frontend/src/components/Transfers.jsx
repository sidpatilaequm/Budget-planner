import { useCallback, useEffect, useState } from 'react'
import { api, currentFyMonth, money, MONTH_FULL, SECTION_NAMES } from '../lib'
import { useUi } from '../ui'
import TransferDialog from './TransferDialog'

const when = (iso) => {
  const d = new Date(iso)
  return `${d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}, ${d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}`
}

export default function Transfers({ yearId, yearStart, can, onChanged }) {
  const { toast, confirm } = useUi()
  const sections = ['expense', 'income'].filter((s) => can(`view_${s}`))
  const [section, setSection] = useState(sections[0])
  const [reg, setReg] = useState(null)
  const [sheet, setSheet] = useState(null)
  const [month, setMonth] = useState('')
  const [open, setOpen] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const [r, s] = await Promise.all([
        api(`/api/years/${yearId}/transfers?section=${section}`),
        api(`/api/years/${yearId}/sections/${section}`),
      ])
      setReg(r); setSheet(s); setError('')
    } catch (e) { setError(e.message) }
  }, [yearId, section])
  useEffect(() => { load() }, [load])

  const canTransfer = can('transfer_budget') && sheet?.heads.some((h) => h.can_edit)

  const reverse = async (t) => {
    if (!await confirm('Reverse this transfer?', `${money(t.amount)} goes back from “${t.to.line}” to “${t.from.line}” in ${t.month_name}.`, 'Reverse transfer')) return
    try {
      const r = await api(`/api/transfers/${t.id}/reverse`, { method: 'POST', body: {} })
      toast(r.warning ? `Transfer reversed. ${r.warning}.` : 'Transfer reversed')
      load(); onChanged()
    } catch (e) { toast(e.message) }
  }

  if (error) return <div className="card"><div className="empty">{error}</div></div>
  if (!reg || !sheet) return <div className="loading">Loading…</div>
  const rows = reg.transfers.filter((t) => month === '' || t.month === +month)
  const editableCodes = new Set(sheet.heads.filter((h) => h.can_edit).map((h) => h.code))

  return (
    <div className="cards">
      <div className="card">
        <div className="cardhead">
          <div><h2>Budget transfers</h2>
            <p className="sub">Move budget between lines in the same month, within a head or from another head. Every transfer is recorded here with its reason, and can be reversed.</p></div>
          <div className="tools">
            {sections.length > 1 && <select value={section} onChange={(e) => setSection(e.target.value)} aria-label="Section">
              {sections.map((s) => <option key={s} value={s}>{SECTION_NAMES[s]}</option>)}</select>}
            <select value={month} onChange={(e) => setMonth(e.target.value)} aria-label="Month">
              <option value="">All months</option>
              {MONTH_FULL.map((m, i) => <option key={i} value={i}>{m}</option>)}
            </select>
            {canTransfer && <button className="btn primary" onClick={() => setOpen(true)}>New transfer</button>}
          </div>
        </div>
        <div className="scroll"><table className="list left">
          <thead><tr><th>When</th><th>Month</th><th>From</th><th>To</th><th className="right">Amount</th><th>Type</th><th>Reason</th><th>By</th><th /></tr></thead>
          <tbody>
            {rows.length ? rows.map((t) => {
              const mayReverse = t.status === 'done' && can('transfer_budget') && editableCodes.has(t.from.head_code) && editableCodes.has(t.to.head_code)
              return (
                <tr key={t.id} style={t.status === 'reversed' ? { opacity: 0.6 } : undefined}>
                  <td>{when(t.created_at)}</td><td>{t.month_name}</td>
                  <td className="wrap-txt" style={{ maxWidth: 220 }}><b>{t.from.line}</b><div className="mut">{t.from.head}</div></td>
                  <td className="wrap-txt" style={{ maxWidth: 220 }}><b>{t.to.line}</b><div className="mut">{t.to.head}</div></td>
                  <td className="right"><b>{money(t.amount)}</b></td>
                  <td>{t.status === 'reversal' ? <span className="tag">Reversal</span>
                    : <span className="tag">{t.kind === 'cross' ? 'From another head' : 'Within head'}</span>}
                    {t.status === 'reversed' && <div className="mut">Reversed</div>}</td>
                  <td className="wrap-txt" style={{ maxWidth: 260 }}>{t.reason}</td>
                  <td>{t.created_by}</td>
                  <td className="right">{mayReverse && <button className="btn ghost sm" onClick={() => reverse(t)}>Reverse</button>}</td>
                </tr>)
            }) : <tr><td colSpan={9}><div className="empty">{reg.transfers.length ? 'No transfers in this month.' : 'No transfers yet in this year.'}{canTransfer ? ' Select New transfer to move budget between lines.' : ''}</div></td></tr>}
          </tbody>
        </table></div>
      </div>

      <div className="card">
        <h2>Net effect by head</h2>
        <p className="sub">Budget moved into and out of each head across the year. Reversals cancel the transfers they undo.</p>
        <div className="scroll"><table className="list">
          <thead><tr><th>Head</th><th>Moved in from other heads</th><th>Moved out to other heads</th><th>Net change</th><th>Moved between its own lines</th></tr></thead>
          <tbody>
            {reg.summary.length ? reg.summary.map((s) => (
              <tr key={s.head_code}><td>{s.head}</td><td>{money(s.in)}</td><td>{money(s.out)}</td>
                <td className={s.net < 0 ? 'down' : s.net > 0 ? 'up' : 'mut'}>{s.net > 0 ? '+' : ''}{money(s.net)}</td>
                <td>{money(s.within)}</td></tr>))
              : <tr><td colSpan={5}><div className="empty">Nothing has moved yet.</div></td></tr>}
          </tbody>
        </table></div>
      </div>

      <TransferDialog open={open} onClose={() => setOpen(false)} yearId={yearId} heads={sheet.heads}
        initialMonth={currentFyMonth(yearStart)}
        onDone={(r) => { setOpen(false); toast(r.warning ? `Transferred. ${r.warning}.` : `Transferred ${money(r.transfer.amount)}`); load(); onChanged() }} />
    </div>
  )
}
