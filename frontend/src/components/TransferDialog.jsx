import { useEffect, useState } from 'react'
import { api, fmt, money, MONTH_FULL, parseNum } from '../lib'
import { Modal } from '../ui'

/**
 * Move budget from one line to another in the same month.
 * `heads` is a section as returned by /sections/{section}; only heads the user can change are offered.
 */
export default function TransferDialog({ open, onClose, yearId, heads, initialFrom, initialMonth = 0, onDone }) {
  const editable = (heads || []).filter((h) => h.can_edit)
  const lineById = Object.fromEntries(editable.flatMap((h) => h.lines.map((l) => [l.id, { ...l, head: h }])))
  const [f, setF] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) return
    const from = initialFrom && lineById[initialFrom] ? lineById[initialFrom] : null
    const fromHead = from?.head.id ?? editable[0]?.id ?? ''
    setF({ month: initialMonth, fromHead, from: from?.id ?? '', toHead: fromHead, to: '', amount: '', reason: '' })
    setErr('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  if (!open || !f) return <Modal open={false} />
  const set = (patch) => setF((x) => ({ ...x, ...patch }))
  const headLines = (hid) => editable.find((h) => h.id === +hid)?.lines || []
  const src = lineById[f.from], dst = lineById[f.to]
  const available = src ? src.m[f.month] : 0
  const amount = parseNum(f.amount)
  const cross = src && dst && src.head.id !== dst.head.id
  const ready = src && dst && src.id !== dst.id && amount > 0 && amount <= available + 0.005 && f.reason.trim().length >= 3

  const submit = async (e) => {
    e.preventDefault()
    if (!ready) return
    setBusy(true); setErr('')
    try {
      const r = await api(`/api/years/${yearId}/transfers`, {
        method: 'POST', body: { from_line_id: src.id, to_line_id: dst.id, month: +f.month, amount, reason: f.reason },
      })
      onDone(r)
    } catch (e2) { setErr(e2.message) } finally { setBusy(false) }
  }

  const lineOptions = (hid, exclude) => headLines(hid).map((l) => (
    <option key={l.id} value={l.id} disabled={l.id === exclude}>{l.name} ({money(l.m[f.month])} in {MONTH_FULL[f.month]})</option>))

  return (
    <Modal open onClose={onClose} wide>
      <form className="dlg" onSubmit={submit} noValidate>
        <h2>Transfer budget</h2>
        <p className="sub">Move budget from one line to another in the same month. The total for the year stays the same.</p>
        {!editable.length && <p className="err">You cannot change any head in this section, so you cannot transfer budget here.</p>}
        <label className="field">Month
          <select value={f.month} onChange={(e) => set({ month: +e.target.value })}>
            {MONTH_FULL.map((m, i) => <option key={i} value={i}>{m}</option>)}
          </select></label>
        <fieldset>
          <legend>From</legend>
          <div className="row2">
            <label className="field">Head
              <select value={f.fromHead} onChange={(e) => set({ fromHead: +e.target.value, from: '' })}>
                {editable.map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}
              </select></label>
            <label className="field">Line
              <select value={f.from} onChange={(e) => set({ from: +e.target.value })}>
                <option value="">Choose a line</option>
                {lineOptions(f.fromHead, f.to)}
              </select></label>
          </div>
          {src && <p className="sub" style={{ margin: 0 }}>Available in {MONTH_FULL[f.month]}: <b>{money(available)}</b></p>}
        </fieldset>
        <fieldset>
          <legend>To</legend>
          <div className="row2">
            <label className="field">Head
              <select value={f.toHead} onChange={(e) => set({ toHead: +e.target.value, to: '' })}>
                {editable.map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}
              </select></label>
            <label className="field">Line
              <select value={f.to} onChange={(e) => set({ to: +e.target.value })}>
                <option value="">Choose a line</option>
                {lineOptions(f.toHead, f.from)}
              </select></label>
          </div>
          {src && dst && <p className="sub" style={{ margin: 0 }}>
            <span className="tag">{cross ? 'From another head' : 'Within the same head'}</span>{' '}
            {cross ? `Budget leaves “${src.head.name}” and joins “${dst.head.name}”.` : `“${src.head.name}” keeps the same total.`}
          </p>}
        </fieldset>
        <div className="row2">
          <label className="field">Amount
            <span className="pctwrap">₹<input className="inp" value={f.amount} inputMode="decimal" onChange={(e) => set({ amount: e.target.value })} />
              {src && available > 0 && <button type="button" className="btn ghost sm" onClick={() => set({ amount: String(available) })}>All</button>}
            </span></label>
          <label className="field">Reason
            <input className="inp" value={f.reason} maxLength={300} placeholder="For example, insurance renewal due in June"
              onChange={(e) => set({ reason: e.target.value })} /></label>
        </div>
        {src && dst && amount > 0 && amount <= available + 0.005 && (
          <div className="preview" style={{ gridTemplateColumns: '1fr 1fr' }}>
            <div><span>{src.name}, {MONTH_FULL[f.month]}</span>{fmt(available)} → {fmt(available - amount)}</div>
            <div><span>{dst.name}, {MONTH_FULL[f.month]}</span>{fmt(dst.m[f.month])} → {fmt(dst.m[f.month] + amount)}</div>
          </div>)}
        {src && amount > available + 0.005 && <p className="err">“{src.name}” has only {money(available)} in {MONTH_FULL[f.month]}.</p>}
        <p className="err" role="alert">{err}</p>
        <div className="dlgbtns">
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={!ready || busy}>Transfer {amount > 0 ? money(amount) : ''}</button>
        </div>
      </form>
    </Modal>
  )
}
