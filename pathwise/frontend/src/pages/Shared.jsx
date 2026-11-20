import { useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'
import { useAuth } from '../auth'
import { useAction, useFetch } from '../hooks'
import { Alert, Badge, Empty, Field, Pagination, Spinner } from '../components/ui'
import { timeAgo } from '../utils'

export function Notifications() {
  const [page, setPage] = useState(1)
  const [unreadOnly, setUnreadOnly] = useState(false)
  const { data, loading, error, reload } = useFetch('/notifications', { page, unread_only: unreadOnly || undefined, page_size: 20 })
  const action = useAction()
  const markRead = (id) => action.run(async () => { await api.post(`/notifications/${id}/read`); reload() })
  const markAll = () => action.run(async () => { await api.post('/notifications/read-all'); reload() })
  const pages = data ? Math.max(1, Math.ceil(data.total / 20)) : 1

  return (
    <div className="container page stack" style={{ maxWidth: 860 }}>
      <div className="page-head">
        <div><h1>Notifications</h1><p>{data ? `${data.unread} unread` : ''}</p></div>
        <div className="row">
          <label className="check"><input type="checkbox" checked={unreadOnly} onChange={(e) => { setUnreadOnly(e.target.checked); setPage(1) }} />Unread only</label>
          <button className="btn secondary small" onClick={markAll} disabled={action.busy || !data?.unread}>Mark all as read</button>
        </div>
      </div>
      <Alert>{error || action.error}</Alert>
      {loading && <Spinner />}
      {data && data.items.length === 0 && <Empty title="Nothing here yet">We will let you know about applications, interviews and new matches.</Empty>}
      <ul className="list-plain">
        {data?.items.map((n) => (
          <li key={n.id} className="card" style={{ borderLeft: n.is_read ? undefined : '4px solid var(--brand)' }}>
            <div className="row between">
              <strong>{n.title}</strong>
              <span className="muted small">{timeAgo(n.created_at)}</span>
            </div>
            {n.body && <p style={{ margin: '0.25rem 0', whiteSpace: 'pre-wrap' }}>{n.body}</p>}
            <div className="row">
              {n.link && <Link to={n.link} onClick={() => !n.is_read && markRead(n.id)}>Open</Link>}
              {!n.is_read && <button className="btn ghost small" onClick={() => markRead(n.id)}>Mark as read</button>}
            </div>
          </li>
        ))}
      </ul>
      <Pagination page={page} pages={pages} onChange={setPage} />
    </div>
  )
}

const EMAIL_PREFS = [
  ['new_recommendations', 'New job recommendations', 'Periodic emails with jobs picked for your profile.', ['candidate']],
  ['high_match_alerts', 'High-match job alerts', 'Be notified when a new job closely fits your CV.', ['candidate']],
  ['application_updates', 'Application updates', 'Status changes on your applications, or new applications to your jobs.', ['candidate', 'employer', 'recruiter']],
  ['interview_invitations', 'Interview invitations', 'Emails when an interview is scheduled.', ['candidate']],
]

export function Account() {
  const { user, refresh } = useAuth()
  const [name, setName] = useState(user.full_name)
  const [prefs, setPrefs] = useState({ ...user.email_preferences })
  const [passwords, setPasswords] = useState({ current_password: '', new_password: '' })
  const [msg, setMsg] = useState({})
  const profileAction = useAction()
  const passAction = useAction()
  const verifyAction = useAction()

  const saveAccount = async (event) => {
    event.preventDefault()
    setMsg({})
    const ok = await profileAction.run(async () => { await api.patch('/auth/me', { full_name: name, email_preferences: prefs }); return true })
    if (ok) { await refresh(); setMsg({ account: 'Settings saved.' }) }
  }
  const changePassword = async (event) => {
    event.preventDefault()
    setMsg({})
    const ok = await passAction.run(async () => { await api.post('/auth/change-password', passwords); return true })
    if (ok) { setPasswords({ current_password: '', new_password: '' }); setMsg({ password: 'Password changed.' }) }
  }
  const resend = async () => {
    const ok = await verifyAction.run(async () => { await api.post('/auth/resend-verification'); return true })
    if (ok) setMsg({ verify: 'Verification email sent.' })
  }

  return (
    <div className="container page stack" style={{ maxWidth: 760 }}>
      <div className="page-head"><div><h1>Account settings</h1><p>{user.email} <Badge tone={user.email_verified ? 'success' : 'warn'}>{user.email_verified ? 'Verified' : 'Not verified'}</Badge></p></div></div>
      {!user.email_verified && (
        <Alert kind="warn">
          Verify your email to receive notifications reliably. <button className="btn ghost small" onClick={resend} disabled={verifyAction.busy}>Resend verification email</button>
          {msg.verify && <span> {msg.verify}</span>}
        </Alert>
      )}
      <form className="card stack" onSubmit={saveAccount}>
        <h2 style={{ margin: 0 }}>Profile and email notifications</h2>
        <Field label="Full name" htmlFor="an"><input id="an" required minLength={2} value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <fieldset style={{ border: 0, padding: 0, margin: 0 }} className="stack-sm">
          <legend style={{ fontWeight: 600, marginBottom: 6 }}>Email me about</legend>
          {EMAIL_PREFS.filter(([, , , roles]) => roles.includes(user.role)).map(([key, label, hint]) => (
            <label key={key} className="check"><input type="checkbox" checked={Boolean(prefs[key])} onChange={(e) => setPrefs({ ...prefs, [key]: e.target.checked })} /><span>{label}<br /><span className="muted small">{hint}</span></span></label>
          ))}
        </fieldset>
        <Alert>{profileAction.error}</Alert>
        <Alert kind="success">{msg.account}</Alert>
        <div><button className="btn" disabled={profileAction.busy}>Save settings</button></div>
      </form>
      <form className="card stack" onSubmit={changePassword}>
        <h2 style={{ margin: 0 }}>Change password</h2>
        <Field label="Current password" htmlFor="cp"><input id="cp" type="password" required autoComplete="current-password" value={passwords.current_password} onChange={(e) => setPasswords({ ...passwords, current_password: e.target.value })} /></Field>
        <Field label="New password" htmlFor="npw" hint="At least 8 characters with letters and numbers"><input id="npw" type="password" required minLength={8} autoComplete="new-password" value={passwords.new_password} onChange={(e) => setPasswords({ ...passwords, new_password: e.target.value })} /></Field>
        <Alert>{passAction.error}</Alert>
        <Alert kind="success">{msg.password}</Alert>
        <div><button className="btn" disabled={passAction.busy}>Change password</button></div>
      </form>
    </div>
  )
}

export function NotFound() {
  return <div className="container page"><Empty title="Page not found" action={<Link className="btn" to="/">Go home</Link>}>The page you are looking for does not exist.</Empty></div>
}
