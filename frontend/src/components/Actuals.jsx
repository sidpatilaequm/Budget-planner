import { useEffect, useRef, useState } from 'react'
import { api, downloadFile, fyNice, money, MONTH_FULL, parseNum } from '../lib'
import { Modal, useLoad, useUi } from '../ui'
import { Badge, SubTabs, todayIso } from './common'

const SOURCES = { manual: 'Entered', import: 'Imported', tally: 'Tally' }

export default function Actuals({ year, can }) {
  const [tab, setTab] = useState('entries')
  const tabs = [['entries', 'Entries']]
  if (can('manage_integration')) tabs.push(['tally', 'Tally'])
  return (
    <>
      <SubTabs tabs={tabs} value={tab} onChange={setTab} />
      {tab === 'entries' ? <Entries year={year} can={can} /> : <TallySetup year={year} />}
    </>
  )
}

// ---------------------------------------------------------------- entries
function Entries({ year, can }) {
  const { toast, confirm } = useUi()
  const [f, setF] = useState({ section: '', month: '', source: '', q: '' })
  const [idx] = useLoad(() => api(`/api/years/${year.id}/lines-index`), [year.id])
  const [tds] = useLoad(() => (can('view_tds') ? api('/api/tds/sections') : Promise.resolve([])), [])
  const query = new URLSearchParams({ fy: year.start, ...Object.fromEntries(Object.entries(f).filter(([, v]) => v !== '')) })
  const [list, reload] = useLoad(() => api(`/api/actuals?${query}`), [query.toString()])
  const [edit, setEdit] = useState(null)
  const fileRef = useRef(null)
  const canEnter = can('enter_actuals')

  const del = async (r) => {
    if (!await confirm('Delete this entry?', `${money(r.amount)} on ${r.line || r.ledger}, ${r.date}.`, 'Delete')) return
    try { await api(`/api/actuals/${r.id}`, { method: 'DELETE' }); toast('Deleted'); reload() } catch (e) { toast(e.message) }
  }
  const importFile = async (file) => {
    const form = new FormData(); form.append('file', file)
    try {
      const r = await api('/api/actuals/import', { method: 'POST', form })
      if (!r.ok) { toast(`Nothing imported. ${r.errors.slice(0, 3).join(' ')}${r.errors.length > 3 ? ` and ${r.errors.length - 3} more` : ''}`); return }
      toast(`${r.rows} entries imported`); reload()
    } catch (e) { toast(e.message) }
  }

  return (
    <div className="cards">
      <div className="card">
        <div className="cardhead"><div><h2>Actual income and expenses, FY {fyNice(year.start)}</h2>
          <p className="sub">Fees and other money received, and expenses paid or booked. Entries from Tally arrive by themselves once Tally is connected; until then, enter them here or import them from Excel. They count against the matching budget line and can be the base for next year’s plan.</p></div>
          {canEnter && <div className="tools">
            <button className="btn primary" onClick={() => setEdit({ date: todayIso(), section: 'expense', head_code: '', line_code: '', amount: '', party: '', voucher_type: 'Payment', voucher_no: '', narration: '', tds_code: '', tds_amount: '' })}>Add entry</button>
            <button className="btn" onClick={() => fileRef.current.click()}>Import Excel</button>
            <button className="btn ghost" onClick={() => downloadFile(`/api/years/${year.id}/actuals-template`, `actuals-template-${year.label}.xlsx`).catch((e) => toast(e.message))}>Download template</button>
            <input ref={fileRef} type="file" accept=".xlsx" hidden onChange={(e) => { const x = e.target.files[0]; e.target.value = ''; if (x) importFile(x) }} />
          </div>}
        </div>
        <div className="toolbar">
          <select value={f.section} onChange={(e) => setF({ ...f, section: e.target.value })} aria-label="Income or expense">
            <option value="">Income and expenses</option><option value="income">Income</option><option value="expense">Expenses</option>
            {can('manage_integration') && <option value="unmapped">Tally ledgers not mapped yet</option>}
          </select>
          <select value={f.month} onChange={(e) => setF({ ...f, month: e.target.value })} aria-label="Month">
            <option value="">Whole year</option>{MONTH_FULL.map((m, i) => <option key={i} value={i}>{m}</option>)}
          </select>
          <select value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })} aria-label="Source">
            <option value="">From anywhere</option>{Object.entries(SOURCES).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
          <input placeholder="Search party, narration, voucher" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} style={{ minWidth: 220 }} />
          <span className="spacer" />
          {list && <span className="mut">Income {money(list.totals.income)} · Expenses {money(list.totals.expense)}</span>}
        </div>
        {!list ? <div className="loading">Loading…</div> : list.rows.length ? (
          <div className="scroll"><table className="list">
            <thead><tr><th>Date</th><th>Budget line</th><th>Party and narration</th><th>Voucher</th><th>Amount</th><th>TDS</th><th>From</th><th /></tr></thead>
            <tbody>{list.rows.map((r) => (
              <tr key={r.id}>
                <td style={{ whiteSpace: 'nowrap' }}>{r.date}</td>
                <td>{r.section === 'unmapped' ? <><Badge tone="warn">Not mapped</Badge> <span className="mut">{r.ledger}</span></> : <><b>{r.line || '—'}</b><div className="mut">{r.head}{r.section === 'income' ? ' · income' : ''}</div></>}</td>
                <td>{r.party}{r.narration && <div className="mut">{r.narration}</div>}</td>
                <td className="mut">{[r.voucher_type, r.voucher_no].filter(Boolean).join(' ')}</td>
                <td className={r.section === 'income' ? 'up' : ''} style={{ whiteSpace: 'nowrap' }}>{money(r.amount)}</td>
                <td className="mut" style={{ whiteSpace: 'nowrap' }}>{r.tds_amount ? `${money(r.tds_amount)}${r.tds_code ? ` · ${r.tds_code}` : ''}` : r.tds_code || ''}</td>
                <td><Badge>{SOURCES[r.source]}</Badge></td>
                <td style={{ whiteSpace: 'nowrap' }}>{canEnter && r.source !== 'tally' && <>
                  <button className="btn ghost sm" onClick={() => setEdit({ ...r, amount: String(r.amount), tds_amount: r.tds_amount ? String(r.tds_amount) : '', tds_code: r.tds_code || '' })}>Edit</button>
                  <button className="btn ghost sm" onClick={() => del(r)}>Delete</button></>}</td>
              </tr>))}
            </tbody></table>
            {list.count > list.rows.length && <p className="mut">Showing the latest {list.rows.length} of {list.count}. Narrow the list with the filters.</p>}
          </div>
        ) : <div className="empty">No entries for this selection yet.</div>}
      </div>
      <Modal open={!!edit} onClose={() => setEdit(null)} wide>
        {edit && idx && <EntryForm entry={edit} idx={idx} tds={tds || []} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload() }} />}
      </Modal>
    </div>
  )
}

function EntryForm({ entry, idx, tds, onClose, onSaved }) {
  const { toast } = useUi()
  const [e, setE] = useState(entry)
  const [err, setErr] = useState('')
  const heads = (idx[e.section] || []).filter((h) => h.can)
  const head = heads.find((h) => h.code === e.head_code)
  const set = (patch) => setE((x) => ({ ...x, ...patch }))
  const save = async (ev) => {
    ev.preventDefault()
    const body = { ...e, amount: parseNum(e.amount), tds_amount: parseNum(e.tds_amount), tds_code: e.tds_code || null }
    if (!body.head_code || !body.line_code) return setErr('Choose the budget line.')
    if (!body.amount) return setErr('Enter the amount.')
    try {
      await api(entry.id ? `/api/actuals/${entry.id}` : '/api/actuals', { method: entry.id ? 'PATCH' : 'POST', body })
      toast('Saved'); onSaved()
    } catch (x) { setErr(x.message) }
  }
  return (
    <form className="dlg" onSubmit={save}>
      <h2>{entry.id ? 'Change entry' : 'Add entry'}</h2>
      <div className="row2">
        <label className="field">Date<input type="date" value={e.date} onChange={(x) => set({ date: x.target.value })} required /></label>
        <label className="field">Kind
          <select value={e.section} onChange={(x) => set({ section: x.target.value, head_code: '', line_code: '', voucher_type: x.target.value === 'income' ? 'Receipt' : 'Payment', tds_code: '', tds_amount: '' })}>
            {idx.expense && <option value="expense">Expense paid or booked</option>}{idx.income && <option value="income">Income received</option>}
          </select></label>
        <label className="field">Head
          <select value={e.head_code} onChange={(x) => set({ head_code: x.target.value, line_code: '' })}>
            <option value="">Choose</option>{heads.map((h) => <option key={h.code} value={h.code}>{h.name}</option>)}
          </select></label>
        <label className="field">Line
          <select value={e.line_code} onChange={(x) => set({ line_code: x.target.value })} disabled={!head}>
            <option value="">Choose</option>{(head?.lines || []).map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
          </select></label>
        <label className="field">Amount (₹, before TDS)<input value={e.amount} inputMode="decimal" onChange={(x) => set({ amount: x.target.value })} placeholder="e.g. 1,20,000" /></label>
        <label className="field">{e.section === 'income' ? 'Received from' : 'Paid to'}<input value={e.party} onChange={(x) => set({ party: x.target.value })} placeholder="Name as on the bill" /></label>
        <label className="field">Voucher type<input value={e.voucher_type} onChange={(x) => set({ voucher_type: x.target.value })} /></label>
        <label className="field">Voucher or receipt no.<input value={e.voucher_no} onChange={(x) => set({ voucher_no: x.target.value })} /></label>
        {e.section === 'expense' && <>
          <label className="field">TDS category
            <select value={e.tds_code} onChange={(x) => set({ tds_code: x.target.value })}>
              <option value="">None, or from the budget line</option>{tds.filter((s) => s.active).map((s) => <option key={s.code} value={s.code}>{s.label} ({s.old_ref})</option>)}
            </select></label>
          <label className="field">TDS deducted (₹)<input value={e.tds_amount} inputMode="decimal" onChange={(x) => set({ tds_amount: x.target.value })} placeholder="0" /></label>
        </>}
      </div>
      <label className="field">Narration<input value={e.narration} onChange={(x) => set({ narration: x.target.value })} /></label>
      {err && <p className="err">{err}</p>}
      <div className="dlgbtns"><button type="button" className="btn ghost" onClick={onClose}>Cancel</button><button className="btn primary">Save</button></div>
    </form>
  )
}

// ---------------------------------------------------------------- Tally
function TallySetup({ year }) {
  const { toast, confirm } = useUi()
  const [st, reloadSt] = useLoad(() => api('/api/tally/settings'), [])
  const [led, reloadLed] = useLoad(() => api('/api/tally/ledgers'), [])
  const [idx] = useLoad(() => api(`/api/years/${year.id}/lines-index`), [year.id])
  const [tds] = useLoad(() => api('/api/tds/sections').catch(() => []), [])
  const [conn, setConn] = useState(null)
  const [key, setKey] = useState('')
  const [range, setRange] = useState({ from: `${year.start}-04-01`, to: todayIso() < `${year.start + 1}-03-31` ? todayIso() : `${year.start + 1}-03-31` })
  const [busy, setBusy] = useState(false)
  const [mapFor, setMapFor] = useState(null)
  useEffect(() => { if (st) setConn({ host: st.host, port: st.port, company: st.company }) }, [st])

  const saveConn = async () => { try { await api('/api/tally/settings', { method: 'PUT', body: conn }); toast('Saved'); reloadSt() } catch (e) { toast(e.message) } }
  const test = async () => { setBusy(true); try { const r = await api('/api/tally/test', { method: 'POST' }); toast(`Connected: ${r.ledgers} ledgers found`); reloadLed() } catch (e) { toast(e.message) } finally { setBusy(false) } }
  const sync = async () => {
    setBusy(true)
    try { const r = await api('/api/tally/sync', { method: 'POST', body: { date_from: range.from, date_to: range.to } }); toast(`${r.vouchers} vouchers, ${r.entries} entries${r.unmapped.length ? `, ${r.unmapped.length} ledgers to map` : ''}`); reloadSt(); reloadLed() } catch (e) { toast(e.message) } finally { setBusy(false) }
  }
  const newKey = async () => {
    if (st?.has_key && !await confirm('Create a new key?', 'The bridge on the Tally computer stops working until you give it the new key.', 'Create new key')) return
    try { setKey((await api('/api/tally/key', { method: 'POST' })).key); reloadSt() } catch (e) { toast(e.message) }
  }
  const lineName = (m) => {
    const h = (idx?.[m.section] || []).find((x) => x.code === m.head_code)
    return h ? `${h.name} › ${(h.lines.find((l) => l.code === m.line_code) || {}).name || '?'}` : '(line not in this year)'
  }
  const removeMap = async (m) => { if (await confirm('Remove this mapping?', `Entries already received stay as they are; new ones from “${m.ledger_name}” will wait to be mapped.`, 'Remove')) { await api(`/api/tally/maps/${m.id}`, { method: 'DELETE' }); reloadLed() } }

  if (!st || !led || !conn) return <div className="loading">Loading…</div>
  const app = window.location.origin
  return (
    <div className="cards">
      <div className="card span6">
        <h2>Connection</h2>
        <p className="sub">{st.last_sync ? <>Last data from Tally {new Date(st.last_sync).toLocaleString()} ({st.last_via === 'bridge' ? 'bridge' : 'direct'}): {st.last_result?.vouchers} vouchers, {st.last_result?.entries} entries{st.last_result?.unmapped ? `, ${st.last_result.unmapped} ledgers to map` : ''}.</> : 'No data from Tally yet.'}</p>
        <h3>Recommended: the Tally bridge</h3>
        <p className="sub">This app runs on the internet and cannot see the Tally computer, so a small program on that computer sends the data. It needs Python 3.9 or later and nothing else.</p>
        <ol className="steps-list">
          <li>In Tally: <b>F1 Help › Settings › Connectivity</b>, set “TallyPrime acts as” to <b>Both</b>, port <b>9000</b>. Keep the company open.</li>
          <li><button className="btn sm" onClick={newKey}>{st.has_key ? 'Create a new integration key' : 'Create an integration key'}</button>{st.has_key && !key && <span className="mut"> Current key ends …{st.key_hint}</span>}
            {key && <div className="keybox"><code>{key}</code><button className="btn ghost sm" onClick={() => navigator.clipboard?.writeText(key).then(() => toast('Copied'))}>Copy</button><div className="mut">Shown only now. Keep it safe; anyone with it can send data.</div></div>}</li>
          <li><button className="btn sm" onClick={() => downloadFile('/api/tally/bridge', 'tally_bridge.py').catch((e) => toast(e.message))}>Download the bridge</button> and save it on the Tally computer.</li>
          <li>Run it once to test, then every 15 minutes with Windows Task Scheduler:<pre className="cmd">python tally_bridge.py --app {app} --key {key || 'YOUR-KEY'} --company "{conn.company || 'Company name in Tally'}"</pre>
            <span className="mut">Or leave it running: add <code>--every 15</code>.</span></li>
        </ol>
      </div>
      <div className="card span6">
        <h3 style={{ marginTop: 0 }}>Or connect directly</h3>
        <p className="sub">Only if this server can reach the Tally computer, for example over a VPN.</p>
        <div className="row3">
          <label className="field">Tally computer (host or IP)<input value={conn.host} onChange={(e) => setConn({ ...conn, host: e.target.value })} placeholder="192.168.1.20" /></label>
          <label className="field">Port<input value={conn.port} inputMode="numeric" onChange={(e) => setConn({ ...conn, port: e.target.value })} /></label>
          <label className="field">Company in Tally<input value={conn.company} onChange={(e) => setConn({ ...conn, company: e.target.value })} /></label>
        </div>
        <div className="tools"><button className="btn" onClick={saveConn}>Save</button><button className="btn" disabled={busy || !st.host} onClick={test}>Test connection</button></div>
        <h3>Bring in vouchers</h3>
        <div className="row3">
          <label className="field">From<input type="date" value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} /></label>
          <label className="field">To<input type="date" value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} /></label>
          <div className="field" style={{ justifyContent: 'flex-end' }}><button className="btn primary" disabled={busy || !st.host} onClick={sync}>{busy ? 'Working…' : 'Sync now'}</button></div>
        </div>
        <p className="mut">Each sync replaces Tally’s entries for the period, so vouchers changed or deleted in Tally are updated here too.</p>
      </div>
      <div className="card">
        <div className="cardhead"><div><h2>Ledger mapping</h2>
          <p className="sub">Tell the planner what each Tally ledger is: an expense or income budget line, the TDS payable ledger, or something to ignore (bank, cash, party and other balance-sheet ledgers). Mapping is by ledger name and applies every year.</p></div>
          <button className="btn" onClick={() => setMapFor({ ledger_name: '', section: 'expense', head_code: '', line_code: '', tds_code: '' })}>Map a ledger</button></div>
        {(led.pending.length > 0 || led.tally_ledgers.length > 0) && <>
          <h3>To map</h3>
          <div className="scroll"><table className="list"><thead><tr><th>Ledger</th><th>Entries waiting</th><th /></tr></thead><tbody>
            {led.pending.map((p) => <tr key={p.ledger_name}><td><b>{p.ledger_name}</b></td><td>{p.entries} · {money(p.amount)}</td><td><button className="btn sm primary" onClick={() => setMapFor({ ledger_name: p.ledger_name, section: 'expense', head_code: '', line_code: '', tds_code: '' })}>Map</button></td></tr>)}
            {led.tally_ledgers.filter((t) => !led.pending.some((p) => p.ledger_name === t.name)).slice(0, 200).map((t) => <tr key={t.name}><td>{t.name} <span className="mut">{t.parent}</span></td><td className="mut">none yet</td><td><button className="btn sm" onClick={() => setMapFor({ ledger_name: t.name, section: /bank|cash|capital|loan|debtor|creditor/i.test(t.parent) ? 'ignore' : 'expense', head_code: '', line_code: '', tds_code: '' })}>Map</button></td></tr>)}
          </tbody></table></div>
        </>}
        <h3>Mapped</h3>
        {led.maps.length ? <div className="scroll"><table className="list"><thead><tr><th>Tally ledger</th><th>Counts as</th><th>TDS</th><th /></tr></thead><tbody>
          {led.maps.map((m) => <tr key={m.id}><td>{m.ledger_name}</td>
            <td>{m.section === 'ignore' ? <span className="mut">Ignored</span> : m.section === 'tds' ? 'TDS deducted' : <>{m.section === 'income' ? 'Income: ' : 'Expense: '}{lineName(m)}</>}</td>
            <td className="mut">{m.tds_code || ''}</td>
            <td style={{ whiteSpace: 'nowrap' }}><button className="btn ghost sm" onClick={() => setMapFor({ ...m, tds_code: m.tds_code || '', head_code: m.head_code || '', line_code: m.line_code || '' })}>Change</button><button className="btn ghost sm" onClick={() => removeMap(m)}>Remove</button></td></tr>)}
        </tbody></table></div> : <div className="empty">Nothing mapped yet.</div>}
      </div>
      <Modal open={!!mapFor} onClose={() => setMapFor(null)} wide>
        {mapFor && idx && <MapForm m={mapFor} idx={idx} tds={tds || []} onClose={() => setMapFor(null)} onSaved={() => { setMapFor(null); reloadLed() }} />}
      </Modal>
    </div>
  )
}

function MapForm({ m, idx, tds, onClose, onSaved }) {
  const { toast } = useUi()
  const [x, setX] = useState(m)
  const [err, setErr] = useState('')
  const head = (idx[x.section] || []).find((h) => h.code === x.head_code)
  const save = async (e) => {
    e.preventDefault()
    try { const r = await api('/api/tally/maps', { method: 'PUT', body: { ...x, tds_code: x.tds_code || null } }); toast(`Mapped${r.updated ? `, ${r.updated} entries updated` : ''}`); onSaved() } catch (er) { setErr(er.message) }
  }
  return (
    <form className="dlg" onSubmit={save}>
      <h2>Map a Tally ledger</h2>
      <label className="field">Ledger name, exactly as in Tally<input value={x.ledger_name} onChange={(e) => setX({ ...x, ledger_name: e.target.value })} disabled={!!m.ledger_name} /></label>
      <label className="field">It is
        <select value={x.section} onChange={(e) => setX({ ...x, section: e.target.value, head_code: '', line_code: '' })}>
          <option value="expense">An expense (its debits count against a budget line)</option>
          <option value="income">Income (its credits count as income)</option>
          <option value="tds">TDS payable (its credits are tax deducted on the voucher)</option>
          <option value="ignore">Ignore: bank, cash, party or other balance-sheet ledger</option>
        </select></label>
      {(x.section === 'expense' || x.section === 'income') && <div className="row2">
        <label className="field">Head<select value={x.head_code} onChange={(e) => setX({ ...x, head_code: e.target.value, line_code: '' })}><option value="">Choose</option>{(idx[x.section] || []).map((h) => <option key={h.code} value={h.code}>{h.name}</option>)}</select></label>
        <label className="field">Line<select value={x.line_code} onChange={(e) => setX({ ...x, line_code: e.target.value })} disabled={!head}><option value="">Choose</option>{(head?.lines || []).map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}</select></label>
      </div>}
      {(x.section === 'expense' || x.section === 'tds') && <label className="field">TDS category {x.section === 'expense' ? '(if payments on this ledger attract TDS)' : ''}
        <select value={x.tds_code} onChange={(e) => setX({ ...x, tds_code: e.target.value })}><option value="">None</option>{tds.map((s) => <option key={s.code} value={s.code}>{s.label} ({s.new_ref}, old {s.old_ref})</option>)}</select></label>}
      {err && <p className="err">{err}</p>}
      <div className="dlgbtns"><button type="button" className="btn ghost" onClick={onClose}>Cancel</button><button className="btn primary">Save</button></div>
    </form>
  )
}
