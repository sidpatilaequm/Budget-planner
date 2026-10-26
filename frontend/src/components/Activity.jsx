import { useMemo, useState } from 'react'
import { api } from '../lib'
import { useLoad } from '../ui'

const when = (iso) => {
  const d = new Date(iso)
  return `${d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}, ${d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}`
}

export default function Activity() {
  const [userId, setUserId] = useState('')
  const [rows, , , error] = useLoad(() => api(`/api/activity?limit=500${userId ? `&user_id=${userId}` : ''}`), [userId])
  const [all] = useLoad(() => api('/api/activity?limit=2000'), [])
  const people = useMemo(() => {
    const m = new Map()
    ;(all || []).forEach((r) => r.user_id && m.set(r.user_id, r.user))
    return [...m.entries()].sort((a, b) => a[1].localeCompare(b[1]))
  }, [all])
  return (
    <div className="cards"><div className="card">
      <div className="cardhead">
        <div><h2>Activity</h2><p className="sub">Sign-ins and changes, newest first. Repeated edits to the same line within 10 minutes are grouped.</p></div>
        <label className="field">Show
          <select value={userId} onChange={(e) => setUserId(e.target.value)}>
            <option value="">Everyone</option>
            {people.map(([id, n]) => <option key={id} value={id}>{n}</option>)}
          </select></label>
      </div>
      {error && <div className="empty">{error}</div>}
      <div className="scroll"><table className="list left">
        <thead><tr><th>When</th><th>User</th><th>Action</th></tr></thead>
        <tbody>
          {!rows ? <tr><td colSpan={3}><div className="loading">Loading…</div></td></tr>
            : rows.length ? rows.map((r) => <tr key={r.id}><td>{when(r.ts)}</td><td>{r.user}</td><td className="wrap-txt">{r.action}</td></tr>)
              : <tr><td colSpan={3}><div className="empty">No activity recorded yet.</div></td></tr>}
        </tbody>
      </table></div>
      {rows?.length === 500 && <p className="sub" style={{ marginTop: 10 }}>Showing the latest 500 entries.</p>}
    </div></div>
  )
}
