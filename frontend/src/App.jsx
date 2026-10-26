import { useCallback, useEffect, useRef, useState } from 'react'
import { api, compact, fyNice, money, setToken, getToken, setUnauthorizedHandler } from './lib'
import { Modal, UiProvider, useUi } from './ui'
import BudgetGrid from './components/BudgetGrid'
import Summary from './components/Summary'
import Plan from './components/Plan'
import Limits from './components/Limits'
import Activity from './components/Activity'
import Users from './components/Users'
import PasswordDialog from './components/PasswordDialog'

const IDLE_MINUTES = 30

export default function App() {
  return <UiProvider><Root /></UiProvider>
}

function Root() {
  const [stage, setStage] = useState('loading') // loading | setup | login | ready
  const [session, setSession] = useState(null)
  const [message, setMessage] = useState('')

  const signOutLocal = useCallback((msg = '') => {
    setToken(null); setSession(null); setMessage(msg); setStage('login')
  }, [])

  useEffect(() => {
    setUnauthorizedHandler((msg) => signOutLocal(msg))
    ;(async () => {
      try {
        if (getToken()) { setSession(await api('/api/auth/me')); setStage('ready'); return }
        const s = await api('/api/auth/status')
        setStage(s.needs_setup ? 'setup' : 'login')
      } catch (e) {
        if (e.status !== 401) { setMessage(e.message); setStage('login') }
      }
    })()
  }, [signOutLocal])

  // Sign out after a period without activity.
  const last = useRef(Date.now())
  useEffect(() => {
    if (stage !== 'ready') return
    const bump = () => { last.current = Date.now() }
    window.addEventListener('pointerdown', bump, true)
    window.addEventListener('keydown', bump, true)
    const t = setInterval(() => {
      if (Date.now() - last.current > IDLE_MINUTES * 60000) {
        api('/api/auth/logout', { method: 'POST' }).catch(() => {})
        signOutLocal(`Signed out after ${IDLE_MINUTES} minutes without activity.`)
      }
    }, 30000)
    return () => { clearInterval(t); window.removeEventListener('pointerdown', bump, true); window.removeEventListener('keydown', bump, true) }
  }, [stage, signOutLocal])

  if (stage === 'loading') return <div className="loading">Loading…</div>
  if (stage !== 'ready') {
    return <SignIn mode={stage} message={message} onDone={(data) => {
      setToken(data.token); setSession(data); setMessage(''); setStage('ready'); last.current = Date.now()
    }} />
  }
  return <Shell session={session} setSession={setSession} onSignOut={async () => {
    try { await api('/api/auth/logout', { method: 'POST' }) } catch { /* ignore */ }
    signOutLocal()
  }} />
}

function SignIn({ mode, message, onDone }) {
  const setup = mode === 'setup'
  const [f, setF] = useState({ name: '', username: '', password: '', password2: '' })
  const [err, setErr] = useState(message)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const submit = async (e) => {
    e.preventDefault()
    if (setup) {
      if (!f.name.trim() || !f.username.trim()) return setErr('Enter a full name and a username.')
      if (f.password.length < 8) return setErr('Use a password of at least 8 characters.')
      if (f.password !== f.password2) return setErr('The two passwords do not match.')
    }
    setBusy(true)
    try {
      const data = await api(setup ? '/api/auth/setup' : '/api/auth/login', {
        method: 'POST', body: setup ? { name: f.name, username: f.username, password: f.password } : { username: f.username, password: f.password },
      })
      onDone(data)
    } catch (e2) { setErr(e2.message) } finally { setBusy(false) }
  }
  return (
    <div className="auth">
      <form className="authcard" onSubmit={submit} noValidate>
        <h1>Budget planner</h1>
        <p className="sub">{setup ? 'Create the administrator account. You can add other users and roles after signing in.' : 'Sign in to continue.'}</p>
        {setup && <label className="field">Full name<input className="inp" value={f.name} onChange={set('name')} autoComplete="name" autoFocus /></label>}
        <label className="field">Username<input className="inp" value={f.username} onChange={set('username')} autoComplete="username" autoCapitalize="none" autoFocus={!setup} /></label>
        <label className="field">Password<input className="inp" type="password" value={f.password} onChange={set('password')} autoComplete={setup ? 'new-password' : 'current-password'} /></label>
        {setup && <label className="field">Repeat password<input className="inp" type="password" value={f.password2} onChange={set('password2')} autoComplete="new-password" /></label>}
        <p className="err" role="alert">{err}</p>
        <button className="btn primary" disabled={busy}>{setup ? 'Create account and sign in' : 'Sign in'}</button>
      </form>
    </div>
  )
}

function Shell({ session, onSignOut }) {
  const { toast, confirm } = useUi()
  const can = (k) => !!session.perms[k]
  const [years, setYears] = useState([])
  const [yearId, setYearId] = useState(null)
  const [tab, setTab] = useState(null)
  const [stamp, setStamp] = useState(0)
  const [yearsOpen, setYearsOpen] = useState(false)
  const [pwOpen, setPwOpen] = useState(false)
  const fileRef = useRef(null)

  const refreshYears = useCallback(async (select) => {
    const ys = await api('/api/years')
    setYears(ys)
    setYearId((cur) => select ?? (ys.some((y) => y.id === cur) ? cur : ys[ys.length - 1]?.id ?? null))
  }, [])
  useEffect(() => { refreshYears() }, [refreshYears])

  const tabs = []
  if (can('view_expense')) tabs.push(['expense', 'Expenses'])
  if (can('view_income')) tabs.push(['income', 'Income'])
  const both = can('view_expense') && can('view_income')
  if (can('view_summary') && both) tabs.push(['summary', 'Summary'])
  if (can('plan_year') && both) tabs.push(['plan', 'Plan next year'])
  if (can('manage_limits') && can('view_expense')) tabs.push(['limits', 'Budget limits'])
  if (can('view_log')) tabs.push(['activity', 'Activity'])
  if (can('manage_users')) tabs.push(['users', 'Users and roles'])
  const activeTab = tabs.some((t) => t[0] === tab) ? tab : tabs[0]?.[0]
  const year = years.find((y) => y.id === yearId)

  const changed = () => refreshYears()
  const goToYear = async (id, t = 'expense') => { await refreshYears(id); setTab(t); setStamp((s) => s + 1) }

  const download = async () => {
    try {
      const res = await api(`/api/years/${yearId}/export`, { raw: true })
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `Budget_${year.label}.xlsx`
      document.body.appendChild(a); a.click(); a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 2000)
      toast('Excel file downloaded')
    } catch (e) { toast(e.message) }
  }

  const importFile = async (file) => {
    const send = async (replace) => {
      const form = new FormData()
      form.append('file', file)
      const q = new URLSearchParams({ replace: String(replace) })
      if (year) q.set('year_start', String(year.start))
      return api(`/api/import?${q}`, { method: 'POST', form })
    }
    try {
      let r
      try { r = await send(false) } catch (e) {
        if (e.status !== 409) throw e
        if (!await confirm('Replace existing lines?', e.message, 'Import')) return
        r = await send(true)
      }
      await goToYear(r.year.id)
      toast(`Imported ${r.parts} into FY ${fyNice(r.year.start)}`)
    } catch (e) { toast(e.message) }
  }

  return (
    <>
      <header className="top">
        <div className="wrap bar">
          <div className="brand">Budget planner</div>
          <label><span className="sr">Financial year</span>
            <select value={yearId ?? ''} onChange={(e) => { setYearId(+e.target.value); setStamp((s) => s + 1) }}>
              {years.map((y) => <option key={y.id} value={y.id}>FY {fyNice(y.start)}</option>)}
            </select>
          </label>
          {can('manage_years') && <button className="btn ghost" onClick={() => setYearsOpen(true)}>Manage years</button>}
          <span className="spacer" />
          {can('import') && <>
            <button className="btn ghost" onClick={() => fileRef.current.click()}>Import Excel</button>
            <input ref={fileRef} type="file" accept=".xlsx" hidden onChange={(e) => { const f = e.target.files[0]; e.target.value = ''; if (f) importFile(f) }} />
          </>}
          {can('export') && (can('view_expense') || can('view_income')) && year && <button className="btn" onClick={download}>Download Excel</button>}
          <div className="who">
            <div><b>{session.user.name}</b><div className="role">{session.user.role}</div></div>
            <button className="btn ghost sm" onClick={() => setPwOpen(true)}>Change password</button>
            <button className="btn sm" onClick={onSignOut}>Sign out</button>
          </div>
        </div>
        <nav className="wrap tabs" role="tablist" aria-label="Sections">
          {tabs.map(([k, l]) => <button key={k} role="tab" aria-selected={k === activeTab} onClick={() => setTab(k)}>{l}</button>)}
        </nav>
      </header>
      <main className="wrap">
        {year && <Balance year={year} can={can} />}
        {!activeTab && <div className="card"><div className="empty">Your role does not give access to any part of the budget. Ask an administrator to change your role.</div></div>}
        {year && (activeTab === 'expense' || activeTab === 'income') &&
          <BudgetGrid key={`${activeTab}-${yearId}-${stamp}`} yearId={yearId} section={activeTab} onChanged={changed} />}
        {year && activeTab === 'summary' && <Summary key={`${yearId}-${stamp}`} yearId={yearId} />}
        {year && activeTab === 'plan' && <Plan key={`${yearId}-${stamp}`} years={years} yearId={yearId} can={can} onCreated={(id) => goToYear(id)} />}
        {year && activeTab === 'limits' && <Limits key={`${yearId}-${stamp}`} yearId={yearId} onChanged={changed} />}
        {activeTab === 'activity' && <Activity />}
        {year && activeTab === 'users' && <Users yearId={yearId} me={session.user} />}
      </main>
      <YearsDialog open={yearsOpen} onClose={() => setYearsOpen(false)} years={years} yearId={yearId}
        onDone={async (id, msg) => { await goToYear(id ?? undefined); toast(msg) }} />
      <PasswordDialog open={pwOpen} onClose={() => setPwOpen(false)} />
    </>
  )
}

function Balance({ year, can }) {
  const inc = year.income ?? 0, exp = year.expense ?? 0, net = inc - exp
  const both = can('view_expense') && can('view_income')
  const ratio = inc > 0 ? Math.round((exp / inc) * 1000) / 10 : null
  return (
    <section className="balance" aria-live="polite">
      <div className="fy"><small>Financial year, April to March</small>FY {fyNice(year.start)}</div>
      <div className="eq">
        {can('view_income') && <Term label="Income" value={inc} cls="inc" />}
        {both && <div className="op" aria-hidden="true">−</div>}
        {can('view_expense') && <Term label="Expenses" value={exp} cls="exp" />}
        {both && <><div className="op" aria-hidden="true">=</div><Term label={net < 0 ? 'Deficit' : 'Surplus'} value={net} /></>}
      </div>
      {both && <p className="ratio">{ratio === null ? 'Add income lines to see how much of it your expenses use.' : <>Expenses use <b>{ratio}%</b> of income.</>}</p>}
    </section>
  )
}
const Term = ({ label, value, cls = '' }) => (
  <div className="term"><span className="lbl">{label}</span><span className={`val ${cls}`}>{compact(value)}</span><span className="full">{money(value)}</span></div>
)

function YearsDialog({ open, onClose, years, yearId, onDone }) {
  const { confirm, toast } = useUi()
  const [start, setStart] = useState('')
  const [src, setSrc] = useState('')
  useEffect(() => {
    if (open) {
      setStart(String(Math.max(...years.map((y) => y.start), 2025) + 1))
      setSrc(`lines:${yearId}`)
    }
  }, [open, years, yearId])
  const create = async (e) => {
    e.preventDefault()
    const [source, from] = src.split(':')
    const body = { start: +start, source, from_year_id: from ? +from : null, replace: false }
    try {
      let y
      try { y = await api('/api/years', { method: 'POST', body }) } catch (err) {
        if (err.status !== 409) throw err
        if (!await confirm(`Replace FY ${fyNice(+start)}?`, 'That year already exists. Replacing it overwrites its heads, lines and amounts.', 'Replace year')) return
        y = await api('/api/years', { method: 'POST', body: { ...body, replace: true } })
      }
      onClose(); onDone(y.id, `FY ${fyNice(y.start)} added`)
    } catch (err) { toast(err.message) }
  }
  const remove = async (y) => {
    onClose()
    if (!await confirm(`Delete FY ${fyNice(y.start)}?`, 'All heads, lines and amounts in this year will be removed. This cannot be undone.', 'Delete year')) return
    try { await api(`/api/years/${y.id}`, { method: 'DELETE' }); onDone(null, `FY ${fyNice(y.start)} deleted`) } catch (err) { toast(err.message) }
  }
  return (
    <Modal open={open} onClose={onClose}>
      <form className="dlg" onSubmit={create}>
        <h2>Financial years</h2>
        <div className="yrlist">
          {years.map((y) => (
            <div key={y.id}><b>FY {fyNice(y.start)}</b>
              <small>{y.income !== undefined && `Income ${compact(y.income)}`}{y.income !== undefined && y.expense !== undefined && ', '}{y.expense !== undefined && `expenses ${compact(y.expense)}`}</small>
              <button type="button" className="btn ghost danger" disabled={years.length < 2} onClick={() => remove(y)}>Delete</button></div>
          ))}
        </div>
        <h2 style={{ fontSize: 15, marginTop: 6 }}>Add a year</h2>
        <div className="row3" style={{ gridTemplateColumns: '1fr 2fr', gap: 12 }}>
          <label className="field">Starts in April of<input className="inp" value={start} onChange={(e) => setStart(e.target.value)} inputMode="numeric" /></label>
          <label className="field">Start from
            <select value={src} onChange={(e) => setSrc(e.target.value)}>
              {years.map((y) => [
                <option key={`l${y.id}`} value={`lines:${y.id}`}>Lines from FY {fyNice(y.start)}, amounts cleared</option>,
                <option key={`f${y.id}`} value={`full:${y.id}`}>Lines and amounts from FY {fyNice(y.start)}</option>])}
              <option value="template">Standard heads and lines</option>
            </select>
          </label>
        </div>
        <div className="dlgbtns">
          <button type="button" className="btn ghost" onClick={onClose}>Close</button>
          <button className="btn primary">Add year</button>
        </div>
      </form>
    </Modal>
  )
}
