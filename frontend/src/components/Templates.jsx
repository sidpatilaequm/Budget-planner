import { useRef, useState } from 'react'
import { api, downloadFile, fyNice, money } from '../lib'
import { useUi } from '../ui'

export default function Templates({ year, can, onChanged }) {
  const { toast } = useUi()
  const [amounts, setAmounts] = useState(true)
  const [file, setFile] = useState(null)
  const [report, setReport] = useState(null)
  const [busy, setBusy] = useState(false)
  const fileRef = useRef(null)
  const mayUpload = can('edit_expense') || can('edit_income')
  const origin = window.location.origin

  const download = async () => {
    try {
      await downloadFile(`/api/years/${year.id}/template?amounts=${amounts}`, `Budget_template_${year.label}${amounts ? '' : '_blank'}.xlsx`)
      toast('Template downloaded')
    } catch (e) { toast(e.message) }
  }

  const send = async (apply) => {
    if (!file) return
    setBusy(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const r = await api(`/api/years/${year.id}/template/upload?apply=${apply}`, { method: 'POST', form })
      setReport({ ...r, checkedOnly: !apply })
      if (r.applied) {
        toast('Changes saved')
        onChanged()
      }
    } catch (e) { toast(e.message); setReport(null) } finally { setBusy(false) }
  }

  const s = report?.summary
  const changed = s ? s.updated + s.added_lines + s.added_heads : 0

  return (
    <div className="cards">
      <div className="card span6">
        <h2>1. Download the template</h2>
        <p className="sub">An Excel file with every head and line of FY {fyNice(year.start)}, one row per line, with columns for April to March.</p>
        <fieldset>
          <legend>Amounts in the file</legend>
          <label className="radio"><input type="radio" checked={amounts} onChange={() => setAmounts(true)} /> Current amounts, to review and change</label>
          <label className="radio"><input type="radio" checked={!amounts} onChange={() => setAmounts(false)} /> Headings only, with the amounts blank</label>
        </fieldset>
        <p className="plan-note">Keep the Head code and Line code columns as they are; they link each row to the planner. To add a line, add a row with the head and a line name and no line code. A new head name adds a new head.</p>
        <div className="dlgbtns" style={{ justifyContent: 'flex-start', marginTop: 12 }}>
          <button className="btn primary" onClick={download}>Download template</button>
        </div>
      </div>

      <div className="card span6">
        <h2>2. Upload the filled template</h2>
        {!mayUpload ? <p className="sub">Your role cannot change budget amounts, so it cannot upload a template.</p> : <>
          <p className="sub">Check the file first. Nothing is saved until every row is valid, and lines left out of the file are not deleted.</p>
          <div className="tools">
            <button className="btn" onClick={() => fileRef.current.click()}>Choose file</button>
            <span className="mut">{file ? file.name : 'No file chosen'}</span>
            <input ref={fileRef} type="file" accept=".xlsx" hidden
              onChange={(e) => { setFile(e.target.files[0] || null); setReport(null); e.target.value = '' }} />
          </div>
          <div className="dlgbtns" style={{ justifyContent: 'flex-start', marginTop: 14 }}>
            <button className="btn" disabled={!file || busy} onClick={() => send(false)}>Check file</button>
            <button className="btn primary" disabled={!file || busy || !report || !report.checkedOnly || report.errors.length > 0 || changed === 0}
              onClick={() => send(true)}>Save changes</button>
          </div>
          {file && !report && <p className="plan-note">Select Check file to see what will change.</p>}
        </>}
      </div>

      {report && (
        <div className="card">
          <h2>{report.applied ? 'Saved' : report.errors.length ? 'The file has problems' : report.checkedOnly ? 'Check complete' : 'Nothing to save'}</h2>
          <p className="sub">
            {report.file}: {s.updated} line{s.updated === 1 ? '' : 's'} {report.applied ? 'updated' : 'to update'}, {s.added_lines} line{s.added_lines === 1 ? '' : 's'} and {s.added_heads} head{s.added_heads === 1 ? '' : 's'} {report.applied ? 'added' : 'to add'}, {s.unchanged} unchanged.
            {report.errors.length > 0 && ' Nothing was saved. Correct these rows in Excel, then choose the file again and check it.'}
            {!report.errors.length && report.checkedOnly && changed > 0 && ' Select Save changes to apply them.'}
            {!report.errors.length && changed === 0 && ' The file matches the planner.'}
          </p>
          {report.warnings.map((w, i) => <p key={i} className="warnbox">{w}</p>)}
          {report.errors.length > 0 && <div className="scroll"><table className="list left">
            <thead><tr><th>Sheet</th><th>Row</th><th>Problem</th></tr></thead>
            <tbody>{report.errors.map((e, i) => <tr key={i}><td>{e.sheet}</td><td>{e.row ?? '–'}</td><td className="wrap-txt down">{e.message}</td></tr>)}</tbody>
          </table></div>}
          {report.changes.length > 0 && <div className="scroll" style={{ marginTop: 12 }}><table className="list">
            <thead><tr><th>Sheet</th><th>Row</th><th className="lt">Change</th><th className="lt">Head</th><th className="lt">Line</th><th>Year total before</th><th>After</th></tr></thead>
            <tbody>{report.changes.map((c, i) => <tr key={i}><td>{c.sheet}</td><td>{c.row}</td><td className="lt">{c.action}</td>
              <td className="lt">{c.head}</td><td className="lt">{c.line}</td><td>{money(c.before)}</td><td><b>{money(c.after)}</b></td></tr>)}</tbody>
          </table></div>}
        </div>
      )}

      <div className="card">
        <h2>Upload from a program</h2>
        <p className="sub">For uploading from a script or a scheduled job. It needs only Python 3, nothing else installed, and checks the file unless you add --apply.</p>
        <pre className="code">{`python upload_budget.py --server ${origin} --user YOUR_USERNAME --year ${year.start} --file Budget_template_${year.label}.xlsx
python upload_budget.py --server ${origin} --user YOUR_USERNAME --year ${year.start} --file Budget_template_${year.label}.xlsx --apply`}</pre>
        <p className="plan-note">It asks for your password, or reads it from the BUDGET_PASSWORD environment variable. It prints any problems row by row, and exits with 1 when the file has errors.</p>
        <div className="dlgbtns" style={{ justifyContent: 'flex-start', marginTop: 10 }}>
          <button className="btn" onClick={() => downloadFile('/api/tools/upload_budget.py', 'upload_budget.py').catch((e) => toast(e.message))}>Download the upload program</button>
        </div>
      </div>
    </div>
  )
}
