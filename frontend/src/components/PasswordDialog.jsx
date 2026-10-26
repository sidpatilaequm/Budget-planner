import { useEffect, useState } from 'react'
import { api } from '../lib'
import { Modal, useUi } from '../ui'

export default function PasswordDialog({ open, onClose, user }) {
  // Without `user`: change your own password. With `user`: an administrator resets theirs.
  const { toast } = useUi()
  const [f, setF] = useState({ old: '', n1: '', n2: '' })
  const [err, setErr] = useState('')
  useEffect(() => { if (open) { setF({ old: '', n1: '', n2: '' }); setErr('') } }, [open])
  const save = async (e) => {
    e.preventDefault()
    if (f.n1.length < 8) return setErr('Use a password of at least 8 characters.')
    if (f.n1 !== f.n2) return setErr('The two new passwords do not match.')
    try {
      if (user) await api(`/api/users/${user.id}/password`, { method: 'POST', body: { password: f.n1 } })
      else await api('/api/auth/password', { method: 'POST', body: { old_password: f.old, new_password: f.n1 } })
      onClose(); toast('Password saved')
    } catch (e2) { setErr(e2.message) }
  }
  return (
    <Modal open={open} onClose={onClose}>
      <form className="dlg" onSubmit={save} noValidate>
        <h2>{user ? `Reset password for ${user.name}` : 'Change your password'}</h2>
        {user && <p className="sub">Give the new password to them; they can change it after signing in.</p>}
        {!user && <label className="field">Current password<input className="inp" type="password" value={f.old} onChange={(e) => setF({ ...f, old: e.target.value })} autoComplete="current-password" autoFocus /></label>}
        <label className="field">New password<input className="inp" type="password" value={f.n1} onChange={(e) => setF({ ...f, n1: e.target.value })} autoComplete="new-password" autoFocus={!!user} /></label>
        <label className="field">Repeat new password<input className="inp" type="password" value={f.n2} onChange={(e) => setF({ ...f, n2: e.target.value })} autoComplete="new-password" /></label>
        <p className="err" role="alert">{err}</p>
        <div className="dlgbtns">
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary">Save password</button>
        </div>
      </form>
    </Modal>
  )
}
