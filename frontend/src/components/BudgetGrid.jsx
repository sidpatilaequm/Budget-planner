import { useEffect, useMemo, useState } from 'react'
import { api, fmt, fmtIn, instOf, INST, money, MONTH_FULL, MONTHS, parseNum, parseOpt, SECTION_NAMES, spread, sum } from '../lib'
import { Chevron, useUi } from '../ui'
import SpreadDialog from './SpreadDialog'

const Z = () => <span className="z">–</span>
const cell = (n) => (n ? fmt(n) : <Z />)

export default function BudgetGrid({ yearId, section, onChanged }) {
  const { toast, confirm } = useUi()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [closed, setClosed] = useState({})
  const [showInst, setShowInst] = useState(true)
  const [spreadLine, setSpreadLine] = useState(null)
  const inc = section === 'income'

  const load = async () => {
    try {
      const d = await api(`/api/years/${yearId}/sections/${section}`)
      setData(d)
      // Users limited to some heads start with the other heads collapsed.
      setClosed((c) => (Object.keys(c).length ? c : Object.fromEntries(d.heads.filter((h) => !h.can_edit && d.heads.some((x) => x.can_edit)).map((h) => [h.id, true]))))
    } catch (e) { setError(e.message) }
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load() }, [yearId, section])

  const totals = useMemo(() => {
    if (!data) return null
    const g = Array(12).fill(0)
    const heads = data.heads.map((h) => {
      const m = Array(12).fill(0)
      let qty = null
      h.lines.forEach((l) => { l.m.forEach((v, k) => { m[k] += +v || 0 }); if (l.qty != null) qty = (qty || 0) + l.qty })
      m.forEach((v, k) => { g[k] += v })
      return { m, tot: sum(m), qty }
    })
    const gq = heads.some((h) => h.qty != null) ? sum(heads.map((h) => h.qty || 0)) : null
    return { heads, g, gt: sum(g), gq }
  }, [data])

  if (error) return <div className="card"><div className="empty">{error}</div></div>
  if (!data) return <div className="loading">Loading…</div>

  const hasLimits = !inc && (data.total_limit != null || data.heads.some((h) => h.limit != null))
  const cols = []
  for (let k = 0; k < 12; k++) {
    cols.push({ t: 'm', k })
    if (showInst && (k === 3 || k === 7 || k === 11)) cols.push({ t: 'i', k: (k + 1) / 4 - 1 })
  }
  cols.push({ t: 'tot' }, { t: 'pct' })
  if (hasLimits) cols.push({ t: 'lim' }, { t: 'left' })
  const ncols = 1 + (inc ? 2 : 0) + cols.length + 1
  const G = totals.gt
  const pct = (t) => (G ? `${Math.round((t / G) * 1000) / 10}%` : <Z />)
  const limCell = (l, a, k) => {
    if (l == null) return <Z />
    if (k === 'lim') return fmt(Math.round(l))
    const d = l - a
    return d < -0.5 ? <span className="over">{fmt(Math.round(-d))} over</span> : <span className="lft">{fmt(Math.round(d))}</span>
  }
  const calc = (c, m, tot, limit) => {
    if (c.t === 'i') return cell(instOf(m, c.k))
    if (c.t === 'tot') return cell(tot)
    if (c.t === 'pct') return pct(tot)
    if (c.t === 'lim' || c.t === 'left') return limit === undefined ? null : limCell(limit, tot, c.t)
    return null
  }
  const anyEditable = data.heads.some((h) => h.can_edit)
  const editableCount = data.heads.filter((h) => h.can_edit).length
  const note = !anyEditable ? 'You can view these figures but not change them.'
    : editableCount < data.heads.length ? 'You can change only the heads assigned to you. Others are view only.' : ''

  // ----- saving -----
  const replaceLine = (line) => setData((d) => ({ ...d, heads: d.heads.map((h) => ({ ...h, lines: h.lines.map((l) => (l.id === line.id ? line : l)) })) }))

  const saveLine = async (line, patch, optimistic) => {
    const before = line
    if (optimistic) replaceLine({ ...line, ...optimistic })
    try {
      const r = await api(`/api/lines/${line.id}`, { method: 'PATCH', body: patch })
      replaceLine(r.line)
      if (r.warning) toast(r.warning + '.')
      onChanged()
      return true
    } catch (e) {
      replaceLine(before)
      toast(e.message)
      if (e.status === 404) load()
      return false
    }
  }
  const commitMonth = (line, k, v) => {
    const m = [...line.m]; m[k] = v ?? 0
    return saveLine(line, { m }, { m })
  }
  const commitQtyRate = (line, field, v) => {
    const qty = field === 'qty' ? v : line.qty
    const rate = field === 'rate' ? v : line.rate
    const m = qty != null && rate != null ? spread(qty * rate, line.spread || 'inst3', line.once, line.m) : line.m
    return saveLine(line, { qty, rate, set_qty_rate: true, m }, { qty, rate, m })
  }
  const run = async (fn, okMsg) => {
    try { await fn(); await load(); onChanged(); if (okMsg) toast(okMsg) } catch (e) { toast(e.message) }
  }
  const addHead = () => run(() => api(`/api/years/${yearId}/sections/${section}/heads`, { method: 'POST', body: { name: 'New head' } }), 'Head added. Rename it in the grid.')
  const addLine = (h) => { setClosed({ ...closed, [h.id]: false }); run(() => api(`/api/heads/${h.id}/lines`, { method: 'POST', body: { name: 'New line' } })) }
  const delLine = async (h, l) => {
    const t = sum(l.m)
    if (t && !await confirm('Delete this line?', `“${l.name}” has ${money(t)} entered for the year. Deleting it removes those amounts.`, 'Delete line')) return
    run(() => api(`/api/lines/${l.id}`, { method: 'DELETE' }))
  }
  const delHead = async (h) => {
    if (!await confirm('Delete this head?', `“${h.name}” and its ${h.lines.length} line${h.lines.length === 1 ? '' : 's'} will be removed from this year.`, 'Delete head')) return
    run(() => api(`/api/heads/${h.id}`, { method: 'DELETE' }))
  }
  const renameHead = (h, name) => {
    if (!name.trim() || name === h.name) return
    run(() => api(`/api/heads/${h.id}`, { method: 'PATCH', body: { name } }))
  }
  const renameLine = (l, name) => {
    if (!name.trim() || name === l.name) return
    saveLine(l, { name }, { name })
  }

  // Paste a block of numbers copied from Excel, starting at the cell pasted into.
  const onPaste = async (e, line, k0) => {
    const txt = e.clipboardData.getData('text')
    if (!/[\t\n]/.test(txt.trim())) return
    e.preventDefault()
    const rows = txt.replace(/\r/g, '').replace(/\n+$/, '').split('\n').map((r) => r.split('\t'))
    const visible = data.heads.flatMap((h) => (closed[h.id] ? [] : h.lines.map((l) => ({ h, l }))))
    const start = visible.findIndex((x) => x.l.id === line.id)
    const updates = []
    let skipped = 0
    rows.forEach((r, i) => {
      const x = visible[start + i]
      if (!x) return
      if (!x.h.can_edit) { skipped++; return }
      const m = [...x.l.m]
      r.forEach((v, c) => { if (k0 + c < 12) m[k0 + c] = parseNum(v) })
      updates.push({ id: x.l.id, m })
    })
    if (!updates.length) return toast('None of those rows can be changed by you.')
    try {
      const r = await api(`/api/years/${yearId}/lines/bulk`, { method: 'POST', body: { lines: updates } })
      r.lines.forEach(replaceLine)
      onChanged()
      toast(`Pasted ${updates.length} row${updates.length === 1 ? '' : 's'}${skipped ? `, skipped ${skipped} you cannot change` : ''}${r.warning ? `. ${r.warning}.` : ''}`)
    } catch (err) { toast(err.message) }
  }

  return (
    <>
      <div className="toolbar">
        {data.can_manage_heads && <button className="btn" onClick={addHead}>Add head</button>}
        <button className="btn ghost" onClick={() => setClosed({})}>Expand all</button>
        <button className="btn ghost" onClick={() => setClosed(Object.fromEntries(data.heads.map((h) => [h.id, true])))}>Collapse all</button>
        <label className="chk"><input type="checkbox" checked={showInst} onChange={(e) => setShowInst(e.target.checked)} /> Show installment subtotals</label>
        {note && <span className="notice">{note}</span>}
        {anyEditable && <span className="hint">Type in any month, or use “Set yearly” on a line to spread an amount. You can paste a row of months from Excel, and type sums like 1200*12.</span>}
      </div>
      <div className="gridwrap">
        <table className={`grid sec-${section}`}>
          <thead><tr>
            <th className="name">Particulars</th>
            {inc && <><th>Students / qty</th><th>Fee / rate</th></>}
            {cols.map((c, i) => <th key={i} className={c.t === 'i' ? 'inst' : undefined}>
              {c.t === 'm' ? MONTHS[c.k] : c.t === 'i' ? INST[c.k].label : { tot: 'Total', pct: '% share', lim: 'Limit', left: 'Left' }[c.t]}</th>)}
            <th className="act"><span className="sr">Actions</span></th>
          </tr></thead>
          <tbody>
            {!data.heads.length && <tr><td colSpan={ncols}><div className="empty">No heads yet.{data.can_manage_heads ? ' Add a head to start listing lines.' : ''}</div></td></tr>}
            {data.heads.map((h, hi) => {
              const ht = totals.heads[hi]
              const open = !closed[h.id]
              return [
                <tr className="head" key={`h${h.id}`}>
                  <td className="name"><div className="namecell">
                    <button className="tog" aria-expanded={open} aria-label="Show lines" onClick={() => setClosed({ ...closed, [h.id]: open })}><Chevron /></button>
                    <TextCell value={h.name} readOnly={!data.can_manage_heads} label="Head name" onCommit={(v) => renameHead(h, v)} />
                    {!h.can_edit && anyEditable && <span className="tag">View only</span>}
                    <span className="cnt">{h.lines.length} line{h.lines.length === 1 ? '' : 's'}</span>
                  </div></td>
                  {inc && <><td className="calc">{ht.qty != null ? fmt(ht.qty) : ''}</td><td className="calc" /></>}
                  {cols.map((c, i) => <td key={i} className={`calc ${c.t === 'i' ? 'i' : c.t}`}>{c.t === 'm' ? cell(ht.m[c.k]) : calc(c, ht.m, ht.tot, h.limit ?? null)}</td>)}
                  <td className="act">{data.can_manage_heads && <button className="del" onClick={() => delHead(h)}>Delete</button>}</td>
                </tr>,
                ...(open ? h.lines.map((l) => (
                  <tr className={`item ${h.can_edit ? '' : 'ro'}`} key={`l${l.id}`}>
                    <td className="name"><div className="namecell"><TextCell value={l.name} readOnly={!h.can_lines} label="Line name" onCommit={(v) => renameLine(l, v)} /></div></td>
                    {inc && <>
                      <NumCell value={l.qty} readOnly={!h.can_edit} col="q" cls="q" label={`${l.name} quantity`} onCommit={(v) => commitQtyRate(l, 'qty', v)} />
                      <NumCell value={l.rate} readOnly={!h.can_edit} col="r" cls="q" label={`${l.name} rate`} onCommit={(v) => commitQtyRate(l, 'rate', v)} />
                    </>}
                    {cols.map((c, i) => c.t === 'm'
                      ? <NumCell key={i} value={l.m[c.k]} readOnly={!h.can_edit} col={String(c.k)} label={`${l.name} ${MONTH_FULL[c.k]}`}
                          onCommit={(v) => commitMonth(l, c.k, v)} onPaste={(e) => onPaste(e, l, c.k)} />
                      : <td key={i} className={`calc ${c.t === 'i' ? 'i' : c.t}`}>{calc(c, l.m, sum(l.m), undefined)}</td>)}
                    <td className="act">
                      {h.can_edit && <button onClick={() => setSpreadLine(l)}>Set yearly</button>}
                      {h.can_lines && <button className="del" aria-label="Delete line" title="Delete line" onClick={() => delLine(h, l)}>✕</button>}
                    </td>
                  </tr>)) : []),
                ...(open && h.can_lines ? [
                  <tr className="addrow" key={`a${h.id}`}><td className="name" style={{ background: 'var(--surface)' }}>
                    <button className="addbtn" onClick={() => addLine(h)}>+ Add line</button></td><td colSpan={ncols - 1} /></tr>] : []),
              ]
            })}
            <tr className="grand">
              <td className="name">Total {SECTION_NAMES[section].toLowerCase()}</td>
              {inc && <><td className="calc">{totals.gq != null ? fmt(totals.gq) : ''}</td><td className="calc" /></>}
              {cols.map((c, i) => <td key={i} className={`calc ${c.t === 'i' ? 'i' : c.t}`}>{c.t === 'm' ? cell(totals.g[c.k]) : calc(c, totals.g, G, data.total_limit ?? null)}</td>)}
              <td className="act" />
            </tr>
          </tbody>
        </table>
      </div>
      <SpreadDialog line={spreadLine} onClose={() => setSpreadLine(null)} onApply={async (patch) => {
        const l = spreadLine
        setSpreadLine(null)
        if (await saveLine(l, patch, { m: patch.m, qty: patch.qty, rate: patch.rate })) toast(`Spread ${money(sum(patch.m))} across the year`)
      }} />
    </>
  )
}

// Moves focus up/down the same column with the arrow keys or Enter.
function navigate(e) {
  if (!['Enter', 'ArrowDown', 'ArrowUp'].includes(e.key)) return
  const t = e.currentTarget
  const table = t.closest('table')
  const sel = t.dataset.col !== undefined ? `input[data-col="${t.dataset.col}"]:not([readonly])` : '.namecell input:not([readonly])'
  const list = [...table.querySelectorAll(sel)]
  const next = list[list.indexOf(t) + (e.key === 'ArrowUp' ? -1 : 1)]
  if (next) { e.preventDefault(); next.focus() } else if (e.key === 'Enter') { e.preventDefault(); t.blur() }
}

function NumCell({ value, readOnly, onCommit, label, col, cls = '', onPaste }) {
  const [draft, setDraft] = useState(null)
  return (
    <td className={`num ${cls}`}>
      <input value={draft ?? fmtIn(value)} readOnly={readOnly} inputMode="decimal" data-col={col} aria-label={label}
        tabIndex={readOnly ? -1 : 0}
        onFocus={(e) => { if (readOnly) return; setDraft(value ? String(value) : ''); const el = e.target; requestAnimationFrame(() => el.select()) }}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => {
          if (draft === null) return
          const v = parseOpt(draft)
          setDraft(null)
          if ((v ?? 0) !== (+value || 0)) onCommit(v)
        }}
        onKeyDown={navigate} onPaste={readOnly ? undefined : onPaste} />
    </td>
  )
}

function TextCell({ value, readOnly, onCommit, label }) {
  const [draft, setDraft] = useState(null)
  return (
    <input value={draft ?? value} readOnly={readOnly} tabIndex={readOnly ? -1 : 0} aria-label={label}
      onFocus={() => !readOnly && setDraft(value)} onChange={(e) => setDraft(e.target.value)}
      onBlur={() => { if (draft !== null && draft.trim() && draft !== value) onCommit(draft.trim()); setDraft(null) }}
      onKeyDown={navigate} />
  )
}
