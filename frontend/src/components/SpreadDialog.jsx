import { useEffect, useState } from 'react'
import { fmt, MONTH_FULL, MONTHS, parseNum, parseOpt, spread, sum } from '../lib'
import { Modal } from '../ui'

const PATTERNS = [
  ['equal', 'Equally over 12 months'],
  ['inst3', 'In 3 installments (April, August, December)'],
  ['quarterly', 'Quarterly (April, July, October, January)'],
  ['once', 'Once, in'],
  ['keep', 'Keep the current monthly pattern'],
]

export default function SpreadDialog({ line, onClose, onApply }) {
  const [qty, setQty] = useState('')
  const [rate, setRate] = useState('')
  const [amt, setAmt] = useState('')
  const [pat, setPat] = useState('equal')
  const [once, setOnce] = useState(0)

  useEffect(() => {
    if (!line) return
    const t = sum(line.m)
    setQty(line.qty ?? ''); setRate(line.rate ?? '')
    setAmt(t ? fmt(t) : '')
    setPat(t ? 'keep' : line.spread || 'equal')
    setOnce(line.once || 0)
  }, [line])

  const q = parseOpt(qty), r = parseOpt(rate)
  const total = q != null && r != null ? q * r : parseNum(amt)
  const m = line ? spread(total, pat, once, line.m) : []

  const apply = (e) => {
    e.preventDefault()
    onApply({ m, qty: q, rate: r, set_qty_rate: true, ...(pat !== 'keep' ? { spread: pat } : {}), once: +once })
  }

  return (
    <Modal open={!!line} onClose={onClose}>
      {line && (
        <form className="dlg" onSubmit={apply}>
          <h2>Set a yearly amount</h2>
          <p className="sub">{line.name}</p>
          <div className="row3">
            <label className="field">Quantity (students, units)<input className="inp" value={qty} inputMode="decimal" onChange={(e) => setQty(e.target.value)} /></label>
            <span className="x">×</span>
            <label className="field">Rate per unit<input className="inp" value={rate} inputMode="decimal" onChange={(e) => setRate(e.target.value)} /></label>
          </div>
          <label className="field">Yearly amount
            <input className="inp" inputMode="decimal" autoFocus value={q != null && r != null ? fmt(q * r) : amt}
              onChange={(e) => { setAmt(e.target.value); setQty(''); setRate('') }} />
          </label>
          <fieldset>
            <legend>Spread across the year</legend>
            {PATTERNS.map(([k, label]) => (
              <label className="radio" key={k}>
                <input type="radio" name="pat" checked={pat === k} onChange={() => setPat(k)} /> {label}
                {k === 'once' && <select value={once} onFocus={() => setPat('once')} onChange={(e) => { setOnce(+e.target.value); setPat('once') }}>
                  {MONTH_FULL.map((mn, i) => <option key={i} value={i}>{mn}</option>)}
                </select>}
              </label>
            ))}
          </fieldset>
          <div className="preview">{m.map((v, k) => <div key={k}><span>{MONTHS[k]}</span>{v ? fmt(v) : '–'}</div>)}</div>
          <div className="dlgbtns">
            <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
            <button className="btn primary">Apply to line</button>
          </div>
        </form>
      )}
    </Modal>
  )
}
