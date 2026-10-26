import { useEffect, useState } from 'react'
import { api, SECTION_NAMES } from '../lib'
import { Modal, useLoad, useUi } from '../ui'
import PasswordDialog from './PasswordDialog'

export default function Users({ yearId, me }) {
  const { toast, confirm } = useUi()
  const [users, reloadUsers] = useLoad(() => api('/api/users'), [])
  const [roles, reloadRoles, setRoles] = useLoad(() => api('/api/roles'), [])
  const [meta] = useLoad(() => api('/api/auth/me'), [])
  const [editing, setEditing] = useState(null) // user object, {} for new, null closed
  const [pwUser, setPwUser] = useState(null)
  const [roleNames, setRoleNames] = useState({})

  if (!users || !roles || !meta) return <div className="loading">Loading…</div>
  const groups = meta.perm_groups

  const togglePerm = async (role, key, value) => {
    setRoles(roles.map((r) => (r.id === role.id ? { ...r, perms: { ...r.perms, [key]: value } } : r)))
    try { await api(`/api/roles/${role.id}`, { method: 'PATCH', body: { perms: { [key]: value } } }); reloadRoles() } catch (e) { toast(e.message); reloadRoles() }
  }
  const renameRole = async (role) => {
    const name = (roleNames[role.id] ?? role.name).trim()
    setRoleNames((x) => { const n = { ...x }; delete n[role.id]; return n })
    if (!name || name === role.name) return
    try { await api(`/api/roles/${role.id}`, { method: 'PATCH', body: { name } }); reloadRoles(); reloadUsers() } catch (e) { toast(e.message) }
  }
  const addRole = async () => {
    try { await api('/api/roles', { method: 'POST', body: { name: 'New role', perms: { view_expense: true, view_income: true, view_summary: true } } }); reloadRoles(); toast('Role added. Rename it and tick its permissions.') } catch (e) { toast(e.message) }
  }
  const delRole = async (r) => {
    if (r.users) return toast(`Move the ${r.users} user${r.users === 1 ? '' : 's'} in “${r.name}” to another role first`)
    if (!await confirm(`Delete role “${r.name}”?`, 'This role has no users, so nobody loses access.', 'Delete role')) return
    try { await api(`/api/roles/${r.id}`, { method: 'DELETE' }); reloadRoles() } catch (e) { toast(e.message) }
  }
  const delUser = async (u) => {
    if (!await confirm(`Delete ${u.name}?`, 'They will no longer be able to sign in. Their past activity stays in the log.', 'Delete user')) return
    try { await api(`/api/users/${u.id}`, { method: 'DELETE' }); reloadUsers(); reloadRoles() } catch (e) { toast(e.message) }
  }
  const scopeText = (u) => {
    if (u.scope !== 'some') return 'All heads'
    const n = u.heads.length
    return `${n} head${n === 1 ? '' : 's'}: ${u.heads.slice(0, 3).map((h) => h.name).join(', ')}${n > 3 ? '…' : ''}`
  }

  return (
    <div className="cards">
      <div className="card">
        <div className="cardhead">
          <div><h2>Users</h2><p className="sub">Each person signs in with their own username. What they can see and change comes from their role, and can be limited to particular heads.</p></div>
          <button className="btn primary" onClick={() => setEditing({})}>Add user</button>
        </div>
        <div className="scroll"><table className="list left">
          <thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Can change</th><th>Status</th><th /></tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td><b>{u.name}</b>{u.id === me.id && <span className="mut"> (you)</span>}</td>
                <td>{u.username}</td><td>{u.role}</td>
                <td className="wrap-txt" style={{ maxWidth: 280 }}>{scopeText(u)}</td>
                <td><span className={`pill ${u.active ? '' : 'off'}`}>{u.active ? 'Active' : 'Inactive'}</span></td>
                <td className="right">
                  <button className="btn ghost sm" onClick={() => setEditing(u)}>Edit</button>
                  <button className="btn ghost sm" onClick={() => setPwUser(u)}>Reset password</button>
                  {u.id !== me.id && <button className="btn ghost sm danger" onClick={() => delUser(u)}>Delete</button>}
                </td>
              </tr>))}
          </tbody>
        </table></div>
      </div>

      <div className="card">
        <div className="cardhead">
          <div><h2>Roles and permissions</h2><p className="sub">Tick what each role is allowed to do. Changes apply straight away. The Administrator role always has every permission.</p></div>
          <button className="btn" onClick={addRole}>Add role</button>
        </div>
        <div className="scroll"><table className="matrix">
          <thead><tr><th>Permission</th>
            {roles.map((r) => (
              <th key={r.id}>
                <input value={roleNames[r.id] ?? r.name} readOnly={r.locked} aria-label="Role name"
                  onChange={(e) => setRoleNames({ ...roleNames, [r.id]: e.target.value })}
                  onBlur={() => renameRole(r)} onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()} />
                <span className="rmeta">{r.users} user{r.users === 1 ? '' : 's'}
                  {!r.locked && <> <button className="btn ghost sm danger" style={{ padding: '0 4px' }} onClick={() => delRole(r)}>Delete</button></>}</span>
              </th>))}
          </tr></thead>
          <tbody>
            {groups.map((g) => [
              <tr className="grp" key={g.group}><td colSpan={roles.length + 1}>{g.group}</td></tr>,
              ...g.items.map((p) => (
                <tr key={p.key}><td>{p.label}</td>
                  {roles.map((r) => (
                    <td key={r.id}><input type="checkbox" checked={!!r.perms[p.key]} disabled={r.locked} aria-label={`${r.name}: ${p.label}`}
                      onChange={(e) => togglePerm(r, p.key, e.target.checked)} /></td>))}
                </tr>)),
            ])}
          </tbody>
        </table></div>
      </div>

      <UserDialog user={editing} roles={roles} yearId={yearId} me={me} onClose={() => setEditing(null)}
        onSaved={() => { setEditing(null); reloadUsers(); reloadRoles(); toast('User saved') }} />
      <PasswordDialog open={!!pwUser} user={pwUser?.id === me.id ? null : pwUser} onClose={() => setPwUser(null)} />
    </div>
  )
}

function UserDialog({ user, roles, yearId, me, onClose, onSaved }) {
  const isNew = user && !user.id
  const [f, setF] = useState(null)
  const [heads, setHeads] = useState([])
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!user) return
    setErr('')
    const deptRole = roles.find((r) => r.name === 'Department editor') || roles[0]
    setF({
      name: user.name || '', username: user.username || '', role_id: user.role_id || deptRole?.id,
      password: '', scope: user.scope || 'all', active: user.active ?? true,
      heads: (user.heads || []).map((h) => `${h.section}:${h.code}`),
    })
    api(`/api/head-catalog?year_id=${yearId}`).then(setHeads).catch(() => setHeads([]))
  }, [user, roles, yearId])

  if (!user || !f) return <Modal open={false} />
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const toggleHead = (key, on) => setF({ ...f, scope: 'some', heads: on ? [...f.heads, key] : f.heads.filter((x) => x !== key) })

  const save = async (e) => {
    e.preventDefault()
    const byKey = Object.fromEntries(heads.map((h) => [`${h.section}:${h.code}`, h]))
    // keep previously assigned heads that are not in this year's list
    const keep = (user.heads || []).filter((h) => !byKey[`${h.section}:${h.code}`] && f.heads.includes(`${h.section}:${h.code}`))
    const body = {
      name: f.name, username: f.username, role_id: +f.role_id, password: f.password || null, scope: f.scope, active: f.active,
      heads: [...f.heads.filter((k) => byKey[k]).map((k) => byKey[k]), ...keep],
    }
    try {
      if (isNew) await api('/api/users', { method: 'POST', body })
      else await api(`/api/users/${user.id}`, { method: 'PATCH', body })
      onSaved()
    } catch (e2) { setErr(e2.message) }
  }

  return (
    <Modal open onClose={onClose} wide>
      <form className="dlg" onSubmit={save} noValidate>
        <h2>{isNew ? 'Add user' : `Edit ${user.name}`}</h2>
        <div className="row2">
          <label className="field">Full name<input className="inp" value={f.name} onChange={set('name')} autoFocus /></label>
          <label className="field">Username<input className="inp" value={f.username} onChange={set('username')} autoCapitalize="none" /></label>
        </div>
        <div className="row2">
          <label className="field">Role<select value={f.role_id} onChange={set('role_id')}>{roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
          <label className="field">{isNew ? 'Password (at least 8 characters)' : 'New password (leave empty to keep)'}
            <input className="inp" type="password" value={f.password} onChange={set('password')} autoComplete="new-password" /></label>
        </div>
        <fieldset>
          <legend>Which heads can this user change?</legend>
          <label className="radio"><input type="radio" checked={f.scope === 'all'} onChange={() => setF({ ...f, scope: 'all' })} /> All heads</label>
          <label className="radio"><input type="radio" checked={f.scope === 'some'} onChange={() => setF({ ...f, scope: 'some' })} /> Only the heads ticked below</label>
          <div className="headpick">
            {['expense', 'income'].map((sec) => [
              <h3 key={sec}>{SECTION_NAMES[sec]}</h3>,
              ...heads.filter((h) => h.section === sec).map((h) => {
                const key = `${h.section}:${h.code}`
                return <label className="radio" key={key}><input type="checkbox" checked={f.heads.includes(key)} onChange={(e) => toggleHead(key, e.target.checked)} /> {h.name}</label>
              }),
            ])}
          </div>
          <p className="sub" style={{ margin: '4px 0 0' }}>Users can still view other heads if their role allows viewing. Adding or deleting heads needs access to all heads.</p>
        </fieldset>
        <label className="chk"><input type="checkbox" checked={f.active} disabled={user.id === me.id} onChange={set('active')} /> Account is active</label>
        <p className="err" role="alert">{err}</p>
        <div className="dlgbtns">
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary">Save user</button>
        </div>
      </form>
    </Modal>
  )
}
