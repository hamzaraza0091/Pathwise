import { useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../api'
import { useAction, useDebounced, useFetch } from '../../hooks'
import { useAuth } from '../../auth'
import { Alert, Badge, Empty, Pagination, Spinner } from '../../components/ui'
import { formatDate } from '../../utils'

export function AdminUsers() {
  const { user: me } = useAuth()
  const [q, setQ] = useState('')
  const [role, setRole] = useState('')
  const [page, setPage] = useState(1)
  const dq = useDebounced(q)
  const { data, loading, error, reload } = useFetch('/admin/users', { q: dq || undefined, role: role || undefined, page, page_size: 20 })
  const action = useAction()
  const patch = (u, body) => action.run(async () => { await api.patch(`/admin/users/${u.id}`, body); reload() })
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1

  return (
    <div className="container page stack">
      <div className="page-head"><div><h1>Users</h1><p>{data ? `${data.total} accounts` : ''}</p></div><Link className="btn secondary" to="/admin/companies">Companies</Link></div>
      <div className="card row">
        <div style={{ flex: 1, minWidth: 220 }}><label className="sr-only" htmlFor="uq">Search users</label><input id="uq" type="search" placeholder="Search name or email" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} /></div>
        <label className="sr-only" htmlFor="ur">Role</label>
        <select id="ur" value={role} onChange={(e) => { setRole(e.target.value); setPage(1) }} style={{ width: 160 }}><option value="">All roles</option>{['candidate', 'employer', 'recruiter', 'admin'].map((r) => <option key={r}>{r}</option>)}</select>
      </div>
      <Alert>{error || action.error}</Alert>
      {loading && <Spinner />}
      {data?.items.length === 0 && <Empty title="No users match" />}
      {data?.items.length > 0 && (
        <div className="card table-wrap">
          <table className="table">
            <thead><tr><th>User</th><th>Role</th><th>Verified</th><th>Joined</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {data.items.map((u) => (
                <tr key={u.id}>
                  <td><strong>{u.full_name}</strong><div className="muted small">{u.email}</div></td>
                  <td>{u.role}</td>
                  <td>{u.email_verified ? <Badge tone="success">Yes</Badge> : <Badge tone="warn">No</Badge>}</td>
                  <td>{formatDate(u.created_at)}</td>
                  <td>{u.is_active ? <Badge tone="success">Active</Badge> : <Badge tone="danger">Suspended</Badge>}</td>
                  <td>
                    {u.id !== me.id && (
                      <div className="row">
                        <button className="btn secondary small" disabled={action.busy} onClick={() => patch(u, { is_active: !u.is_active })}>{u.is_active ? 'Suspend' : 'Reactivate'}</button>
                        <select aria-label={`Role for ${u.full_name}`} value={u.role} disabled={action.busy} onChange={(e) => patch(u, { role: e.target.value })} style={{ width: 120 }}>{['candidate', 'employer', 'recruiter', 'admin'].map((r) => <option key={r}>{r}</option>)}</select>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pagination page={page} pages={pages} onChange={setPage} />
    </div>
  )
}

export function AdminCompanies() {
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const dq = useDebounced(q)
  const { data, loading, error, reload } = useFetch('/admin/companies', { q: dq || undefined, page, page_size: 20 })
  const action = useAction()
  const verify = (c) => action.run(async () => { await api.patch(`/admin/companies/${c.id}`, { is_verified: !c.is_verified }); reload() })
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1
  return (
    <div className="container page stack">
      <div className="page-head"><div><h1>Employers and companies</h1><p>Verify companies so candidates can trust their postings.</p></div></div>
      <div className="card"><label className="sr-only" htmlFor="cq">Search companies</label><input id="cq" type="search" placeholder="Search companies" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} /></div>
      <Alert>{error || action.error}</Alert>
      {loading && <Spinner />}
      {data?.items.length === 0 && <Empty title="No companies yet" />}
      {data?.items.length > 0 && (
        <div className="card table-wrap">
          <table className="table">
            <thead><tr><th>Company</th><th>Industry</th><th>Active jobs</th><th>Status</th><th /></tr></thead>
            <tbody>{data.items.map((c) => (
              <tr key={c.id}>
                <td><strong>{c.name}</strong><div className="muted small">{c.website}</div></td>
                <td>{c.industry || '—'}</td><td>{c.active_jobs}</td>
                <td>{c.is_verified ? <Badge tone="success">Verified</Badge> : <Badge tone="muted">Unverified</Badge>}</td>
                <td><button className="btn secondary small" disabled={action.busy} onClick={() => verify(c)}>{c.is_verified ? 'Remove verification' : 'Verify'}</button></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      <Pagination page={page} pages={pages} onChange={setPage} />
    </div>
  )
}
