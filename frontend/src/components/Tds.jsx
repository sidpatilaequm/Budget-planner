import { useState } from 'react'
import { api, downloadFile, fyNice, money, MONTH_FULL, parseNum, parseOpt } from '../lib'
import { Modal, useLoad, useUi } from '../ui'
import { Badge, Kpi, SubTabs, todayIso } from './common'

const STATUS = { short: ['bad', 'Short deducted'], near: ['warn', 'Near threshold'], excess: ['warn', 'Deducted more'], ok: ['good', 'Correct'], 'not yet': ['', 'Below threshold'] }
const MSTATUS = { paid: ['good', 'Deposited'], due: ['warn', 'Due'], overdue: ['bad', 'Overdue'], nothing: ['', '—'], filed: ['good', 'Filed'] }

export default function Tds({ year, can }) {
  const [tab, setTab] = useState('report')
  const manage = can('manage_tds')
  return (
    <>
      <SubTabs tabs={[['report', 'TDS report'], ['deposits', 'Deposits and returns'], ['parties', 'Payees'], ['lines', 'Budget lines'], ['rates', 'Rates and thresholds']]} value={tab} onChange={setTab} />
      {tab === 'report' && <Report fy={year.start} />}
      {tab === 'deposits' && <Deposits fy={year.start} manage={manage} />}
      {tab === 'parties' && <Parties manage={manage} />}
      {tab === 'lines' && <Lines year={year} manage={manage} />}
      {tab === 'rates' && <Rates manage={manage} />}
    </>
  )
}

function Report({ fy }) {
  const { toast } = useUi()
  const [r] = useLoad(() => api(`/api/tds/report?fy=${fy}`), [fy])
  const [f, setF] = useState('')
  if (!r) return <div className="loading">Loading…</div>
  const rows = f ? r.rows.filter((x) => x.status === f) : r.rows
  const t = r.totals
  return (
    <div className="cards">
      <div className="kpis">
        <Kpi label="Payments that attract TDS" value={money(t.gross)} />
        <Kpi label="Should be deducted" value={money(t.expected)} />
        <Kpi label="Deducted" value={money(t.deducted)} />
        <Kpi label="Short deducted" value={money(t.short)} tone={t.short ? 'bad' : 'good'} />
        <Kpi label="Deposited" value={money(t.paid)} tone={t.paid + 1 < t.deducted ? 'warn' : ''} sub={t.deducted > t.paid ? `${money(t.deducted - t.paid)} to deposit` : ''} />
      </div>
      <div className="card">
        <div className="cardhead"><div><h2>TDS by payee, FY {fyNice(fy)}</h2>
          <p className="sub">Every expense with a TDS category, from its own entry, its Tally ledger, its budget line or its payee. From 1 April 2026 the sections are those of the Income-tax Act, 2025 (section 393); the 1961 Act section is shown for reference. Check unusual cases with your CA.</p></div>
          <div className="tools">
            <select value={f} onChange={(e) => setF(e.target.value)} aria-label="Status"><option value="">All payees</option>{Object.entries(STATUS).map(([k, [, l]]) => <option key={k} value={k}>{l}</option>)}</select>
            <button className="btn" onClick={() => downloadFile(`/api/tds/report.csv?fy=${fy}`, `tds-report-${fy}.csv`).catch((e) => toast(e.message))}>Download</button></div></div>
        {rows.length ? <div className="scroll"><table className="list">
          <thead><tr><th>Payee</th><th>Category</th><th>Paid this year</th><th>Threshold</th><th>Rate</th><th>Should be deducted</th><th>Deducted</th><th>Difference</th><th>Status</th></tr></thead>
          <tbody>{rows.map((x, i) => (
            <tr key={i}>
              <td><b>{x.party}</b><div className="mut">{x.pan || <span className="down">No PAN</span>}</div></td>
              <td>{x.label}<div className="mut">{x.new_ref} · old {x.old_ref}</div></td>
              <td>{money(x.gross)}<div className="mut">{x.payments} payment{x.payments === 1 ? '' : 's'}</div></td>
              <td className="mut">{x.limit}{x.remaining != null && x.remaining > 0 && <div>{money(x.remaining)} to go</div>}</td>
              <td>{x.rate}%{x.rate_note && <div className="mut">{x.rate_note}</div>}</td>
              <td>{money(x.expected)}</td><td>{money(x.deducted)}</td>
              <td className={x.short > 1 ? 'down' : ''}>{x.short ? money(x.short) : '–'}</td>
              <td><Badge tone={STATUS[x.status][0]}>{STATUS[x.status][1]}</Badge></td>
            </tr>))}</tbody></table></div> : <div className="empty">No expenses with a TDS category this year. Give budget lines, Tally ledgers or payees a TDS category to see them here.</div>}
      </div>
    </div>
  )
}

function Deposits({ fy, manage }) {
  const { toast, confirm } = useUi()
  const [r, reload] = useLoad(() => api(`/api/tds/report?fy=${fy}`), [fy])
  const [dep, setDep] = useState(null)
  const [ret, setRet] = useState(null)
  if (!r) return <div className="loading">Loading…</div>
  const saveDep = async (e) => {
    e.preventDefault()
    try { await api('/api/tds/deposits', { method: 'POST', body: { fy, month: +dep.month, amount: parseNum(dep.amount), paid_on: dep.paid_on, challan: dep.challan } }); toast('Deposit recorded'); setDep(null); reload() } catch (x) { toast(x.message) }
  }
  const saveRet = async (e) => {
    e.preventDefault()
    try { await api('/api/tds/returns', { method: 'POST', body: { fy, quarter: ret.quarter, filed_on: ret.filed_on, ack: ret.ack } }); toast('Marked as filed'); setRet(null); reload() } catch (x) { toast(x.message) }
  }
  return (
    <div className="cards">
      <div className="card span6">
        <h2>Monthly deposits</h2>
        <p className="sub">Tax deducted in a month is due by the 7th of the next month; for March, by 30 April. Late payment attracts interest.</p>
        <div className="scroll"><table className="list">
          <thead><tr><th>Month</th><th>Deducted</th><th>Deposited</th><th>Due by</th><th>Status</th><th /></tr></thead>
          <tbody>{r.months.map((m) => (
            <tr key={m.month}><td>{MONTH_FULL[m.month]}</td><td>{m.deducted ? money(m.deducted) : '–'}</td><td>{m.paid ? money(m.paid) : '–'}</td>
              <td className="mut">{m.deducted || m.paid ? m.due : ''}</td><td>{m.status !== 'nothing' && <Badge tone={MSTATUS[m.status][0]}>{MSTATUS[m.status][1]}{m.pending > 0.5 && m.status !== 'paid' ? ` ${money(m.pending)}` : ''}</Badge>}</td>
              <td>{manage && m.pending > 0.5 && <button className="btn sm" onClick={() => setDep({ month: m.month, amount: String(m.pending), paid_on: todayIso(), challan: '' })}>Record deposit</button>}</td></tr>))}
          </tbody></table></div>
        {r.deposits.length > 0 && <><h3>Challans</h3><table className="list"><tbody>{r.deposits.map((d) => (
          <tr key={d.id}><td>{MONTH_FULL[d.month]}</td><td>{money(d.amount)}</td><td className="mut">{d.paid_on} · {d.challan}</td>
            <td>{manage && <button className="btn ghost sm" onClick={async () => { if (await confirm('Remove this deposit?', `${money(d.amount)} for ${MONTH_FULL[d.month]}.`, 'Remove')) { await api(`/api/tds/deposits/${d.id}`, { method: 'DELETE' }); reload() } }}>Remove</button>}</td></tr>))}</tbody></table></>}
      </div>
      <div className="card span6">
        <h2>Quarterly TDS statements</h2>
        <p className="sub">The quarterly statement of TDS on payments other than salary (Form 26Q under the 1961 Act). Due 31 July, 31 October, 31 January and 31 May. Late filing attracts a fee for each day.</p>
        <table className="list"><thead><tr><th>Quarter</th><th>TDS</th><th>Due</th><th>Status</th><th /></tr></thead>
          <tbody>{r.quarters.map((q) => (
            <tr key={q.quarter}><td>{q.label}</td><td>{q.deducted ? money(q.deducted) : '–'}</td><td className="mut">{q.due}</td>
              <td>{q.status !== 'nothing' && <Badge tone={MSTATUS[q.status][0]}>{MSTATUS[q.status][1]}{q.filed_on ? ` ${q.filed_on}` : ''}</Badge>}{q.ack && <div className="mut">{q.ack}</div>}</td>
              <td>{manage && (q.filed_on
                ? <button className="btn ghost sm" onClick={async () => { await api(`/api/tds/returns/${fy}/${q.quarter}`, { method: 'DELETE' }); reload() }}>Not filed</button>
                : q.deducted > 0 && <button className="btn sm" onClick={() => setRet({ quarter: q.quarter, filed_on: todayIso(), ack: '' })}>Mark filed</button>)}</td></tr>))}
          </tbody></table>
      </div>
      <Modal open={!!dep} onClose={() => setDep(null)}>{dep && <form className="dlg" onSubmit={saveDep}><h2>TDS deposit for {MONTH_FULL[dep.month]}</h2>
        <label className="field">Amount (₹)<input value={dep.amount} onChange={(e) => setDep({ ...dep, amount: e.target.value })} /></label>
        <label className="field">Paid on<input type="date" value={dep.paid_on} onChange={(e) => setDep({ ...dep, paid_on: e.target.value })} /></label>
        <label className="field">Challan identification number<input value={dep.challan} onChange={(e) => setDep({ ...dep, challan: e.target.value })} /></label>
        <div className="dlgbtns"><button type="button" className="btn ghost" onClick={() => setDep(null)}>Cancel</button><button className="btn primary">Save</button></div></form>}</Modal>
      <Modal open={!!ret} onClose={() => setRet(null)}>{ret && <form className="dlg" onSubmit={saveRet}><h2>Quarter {ret.quarter} statement filed</h2>
        <label className="field">Filed on<input type="date" value={ret.filed_on} onChange={(e) => setRet({ ...ret, filed_on: e.target.value })} /></label>
        <label className="field">Acknowledgement number<input value={ret.ack} onChange={(e) => setRet({ ...ret, ack: e.target.value })} /></label>
        <div className="dlgbtns"><button type="button" className="btn ghost" onClick={() => setRet(null)}>Cancel</button><button className="btn primary">Save</button></div></form>}</Modal>
    </div>
  )
}

function Parties({ manage }) {
  const { toast, confirm } = useUi()
  const [ps, reload] = useLoad(() => api('/api/tds/parties'), [])
  const [secs] = useLoad(() => api('/api/tds/sections'), [])
  const [p, setP] = useState(null)
  const [err, setErr] = useState('')
  if (!ps || !secs) return <div className="loading">Loading…</div>
  const save = async (e) => {
    e.preventDefault()
    try { await api('/api/tds/parties', { method: 'PUT', body: { ...p, tds_code: p.tds_code || null, lower_rate: parseOpt(p.lower_rate) } }); toast('Saved'); setP(null); reload() } catch (x) { setErr(x.message) }
  }
  return (
    <div className="card">
      <div className="cardhead"><div><h2>Payees</h2><p className="sub">PAN and type decide the rate. Without a PAN the rate is at least 20%. Names must match the party on the entries (or in Tally). The 4th letter of the PAN sets the type: P or H is an individual or HUF.</p></div>
        {manage && <button className="btn primary" onClick={() => { setErr(''); setP({ name: '', pan: '', kind: 'other', tds_code: '', lower_rate: '', lower_cert: '', lower_valid_to: '' }) }}>Add payee</button>}</div>
      {ps.length ? <div className="scroll"><table className="list"><thead><tr><th>Payee</th><th>PAN</th><th>Type</th><th>Usual category</th><th>Lower deduction</th><th /></tr></thead><tbody>
        {ps.map((x) => <tr key={x.id}><td>{x.name}</td><td>{x.pan || <span className="down">None</span>}</td><td>{x.kind === 'individual' ? 'Individual or HUF' : 'Other'}</td>
          <td className="mut">{x.tds_code || ''}</td><td className="mut">{x.lower_rate != null ? `${x.lower_rate}% to ${x.lower_valid_to || '—'} (${x.lower_cert})` : ''}</td>
          <td style={{ whiteSpace: 'nowrap' }}>{manage && <><button className="btn ghost sm" onClick={() => { setErr(''); setP({ ...x, tds_code: x.tds_code || '', lower_rate: x.lower_rate ?? '' }) }}>Edit</button>
            <button className="btn ghost sm" onClick={async () => { if (await confirm('Remove this payee?', x.name, 'Remove')) { await api(`/api/tds/parties/${x.id}`, { method: 'DELETE' }); reload() } }}>Remove</button></>}</td></tr>)}
      </tbody></table></div> : <div className="empty">No payees yet.</div>}
      <Modal open={!!p} onClose={() => setP(null)} wide>{p && <form className="dlg" onSubmit={save}><h2>{p.id ? 'Edit payee' : 'Add payee'}</h2>
        <div className="row2">
          <label className="field">Name (as on the entries)<input value={p.name} onChange={(e) => setP({ ...p, name: e.target.value })} disabled={!!p.id} /></label>
          <label className="field">PAN<input value={p.pan} onChange={(e) => setP({ ...p, pan: e.target.value.toUpperCase() })} maxLength={10} placeholder="ABCDE1234F" /></label>
          <label className="field">Type (when there is no PAN)<select value={p.kind} onChange={(e) => setP({ ...p, kind: e.target.value })}><option value="individual">Individual or HUF</option><option value="other">Firm, company or other</option></select></label>
          <label className="field">Usual TDS category<select value={p.tds_code} onChange={(e) => setP({ ...p, tds_code: e.target.value })}><option value="">None</option>{secs.map((s) => <option key={s.code} value={s.code}>{s.label}</option>)}</select></label>
          <label className="field">Lower-deduction certificate rate (%)<input value={p.lower_rate} onChange={(e) => setP({ ...p, lower_rate: e.target.value })} placeholder="Leave empty if none" /></label>
          <label className="field">Certificate number<input value={p.lower_cert} onChange={(e) => setP({ ...p, lower_cert: e.target.value })} /></label>
          <label className="field">Certificate valid to<input type="date" value={p.lower_valid_to} onChange={(e) => setP({ ...p, lower_valid_to: e.target.value })} /></label>
        </div>
        {err && <p className="err">{err}</p>}
        <div className="dlgbtns"><button type="button" className="btn ghost" onClick={() => setP(null)}>Cancel</button><button className="btn primary">Save</button></div></form>}</Modal>
    </div>
  )
}

function Lines({ year, manage }) {
  const { toast } = useUi()
  const [heads, reload] = useLoad(() => api(`/api/tds/lines?year_id=${year.id}`), [year.id])
  const [secs] = useLoad(() => api('/api/tds/sections'), [])
  const [b, reloadB] = useLoad(() => api(`/api/tds/budget?year_id=${year.id}`), [year.id])
  if (!heads || !secs || !b) return <div className="loading">Loading…</div>
  const setCode = async (h, l, code) => {
    try { await api('/api/tds/lines', { method: 'PUT', body: { head_code: h.head_code, line_code: l.line_code, tds_code: code || null } }); reload(); reloadB() } catch (e) { toast(e.message) }
  }
  return (
    <div className="cards">
      <div className="card span6">
        <h2>TDS category for each expense line</h2>
        <p className="sub">Lines whose payments attract TDS, for example consultants (professional fees), transport contractors, advertising, rent and NBFC loan interest. Used as the default for actuals and for the budgeted TDS. Interest paid to banks does not attract TDS.</p>
        <div className="scroll" style={{ maxHeight: 620 }}><table className="list">
          <tbody>{heads.map((h) => [
            <tr className="ph" key={h.head_code}><td colSpan={2}>{h.head}</td></tr>,
            ...h.lines.map((l) => <tr key={l.line_code}><td>{l.line}<div className="mut">{money(l.budget)}</div></td>
              <td><select value={l.tds_code || ''} disabled={!manage} onChange={(e) => setCode(h, l, e.target.value)} aria-label={`TDS category for ${l.line}`}>
                <option value="">No TDS</option>{secs.filter((s) => s.active).map((s) => <option key={s.code} value={s.code}>{s.label}</option>)}</select></td></tr>),
          ])}</tbody></table></div>
      </div>
      <div className="card span6">
        <h2>Budgeted TDS, FY {fyNice(year.start)}</h2>
        <p className="sub">An estimate of the tax you will deduct and deposit each month, from the budget and the “other payee” rate. Actual deductions depend on each payee and the thresholds.</p>
        <div className="kpis"><Kpi label="TDS in the budget" value={money(b.total)} /></div>
        <table className="list"><thead><tr><th>Month</th><th>TDS</th><th>Deposit by</th></tr></thead>
          <tbody>{b.months.map((v, i) => <tr key={i}><td>{MONTH_FULL[i]}</td><td>{v ? money(v) : '–'}</td><td className="mut">{v ? b.due[i] : ''}</td></tr>)}</tbody></table>
        {b.lines.length > 0 && <><h3>By line</h3><table className="list"><tbody>{b.lines.map((l, i) => <tr key={i}><td>{l.line}<div className="mut">{l.head}</div></td><td className="mut">{l.code} {l.rate}%</td><td>{money(l.tds)}</td></tr>)}</tbody></table></>}
      </div>
    </div>
  )
}

function Rates({ manage }) {
  const { toast } = useUi()
  const [secs, reload] = useLoad(() => api('/api/tds/sections'), [])
  const [s, setS] = useState(null)
  if (!secs) return <div className="loading">Loading…</div>
  const lim = (v) => (v == null ? '—' : money(v))
  const save = async (e) => {
    e.preventDefault()
    try {
      await api('/api/tds/sections', { method: 'PUT', body: { ...s, rate_ind: parseNum(s.rate_ind), rate_other: parseNum(s.rate_other), single_limit: parseOpt(s.single_limit), annual_limit: parseOpt(s.annual_limit), monthly_limit: parseOpt(s.monthly_limit) } })
      toast('Saved'); setS(null); reload()
    } catch (x) { toast(x.message) }
  }
  return (
    <div className="card">
      <div className="cardhead"><div><h2>TDS rates and thresholds</h2><p className="sub">As published for tax year 2026–27 under the Income-tax Act, 2025, which took effect on 1 April 2026; rates and thresholds carry over from the 1961 Act. When the law changes, update the figures here. Confirm them with your CA.</p></div>
        {manage && <button className="btn" onClick={() => setS({ code: '', label: '', new_ref: '', old_ref: '', rate_ind: '', rate_other: '', single_limit: '', annual_limit: '', monthly_limit: '', active: true })}>Add category</button>}</div>
      <div className="scroll"><table className="list"><thead><tr><th>Category</th><th>Section</th><th>Individual/HUF</th><th>Others</th><th>Single payment</th><th>Year</th><th>Month</th><th /></tr></thead>
        <tbody>{secs.map((x) => <tr key={x.code}><td>{x.label}{!x.active && <Badge>Off</Badge>}<div className="mut">{x.code}</div></td><td>{x.new_ref}<div className="mut">old {x.old_ref}</div></td>
          <td>{x.rate_ind}%</td><td>{x.rate_other}%</td><td>{lim(x.single_limit)}</td><td>{lim(x.annual_limit)}</td><td>{lim(x.monthly_limit)}</td>
          <td>{manage && <button className="btn ghost sm" onClick={() => setS({ ...x, single_limit: x.single_limit ?? '', annual_limit: x.annual_limit ?? '', monthly_limit: x.monthly_limit ?? '' })}>Edit</button>}</td></tr>)}</tbody></table></div>
      <Modal open={!!s} onClose={() => setS(null)} wide>{s && <form className="dlg" onSubmit={save}><h2>{s.id ? 'Edit' : 'Add'} TDS category</h2>
        <div className="row2">
          <label className="field">Code<input value={s.code} onChange={(e) => setS({ ...s, code: e.target.value })} disabled={!!s.id} /></label>
          <label className="field">Description<input value={s.label} onChange={(e) => setS({ ...s, label: e.target.value })} /></label>
          <label className="field">Section (2025 Act)<input value={s.new_ref} onChange={(e) => setS({ ...s, new_ref: e.target.value })} /></label>
          <label className="field">Old section (1961 Act)<input value={s.old_ref} onChange={(e) => setS({ ...s, old_ref: e.target.value })} /></label>
          <label className="field">Rate for individual or HUF (%)<input value={s.rate_ind} onChange={(e) => setS({ ...s, rate_ind: e.target.value })} /></label>
          <label className="field">Rate for others (%)<input value={s.rate_other} onChange={(e) => setS({ ...s, rate_other: e.target.value })} /></label>
          <label className="field">Single payment above (₹)<input value={s.single_limit} onChange={(e) => setS({ ...s, single_limit: e.target.value })} placeholder="No limit" /></label>
          <label className="field">Year’s total above (₹)<input value={s.annual_limit} onChange={(e) => setS({ ...s, annual_limit: e.target.value })} placeholder="No limit" /></label>
          <label className="field">Month’s total above (₹)<input value={s.monthly_limit} onChange={(e) => setS({ ...s, monthly_limit: e.target.value })} placeholder="No limit" /></label>
          <label className="chk"><input type="checkbox" checked={s.active} onChange={(e) => setS({ ...s, active: e.target.checked })} /> In use</label>
        </div>
        <div className="dlgbtns"><button type="button" className="btn ghost" onClick={() => setS(null)}>Cancel</button><button className="btn primary">Save</button></div></form>}</Modal>
    </div>
  )
}
