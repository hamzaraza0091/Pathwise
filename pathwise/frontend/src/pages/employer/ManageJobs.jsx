import { useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../api'
import { useAction, useFetch } from '../../hooks'
import { Alert, Badge, Empty, Spinner, Tabs } from '../../components/ui'
import { formatDate } from '../../utils'

const TONE = { active: 'success', closed: 'muted', expired: 'warn', pending_review: 'warn', removed: 'danger' }

export default function ManageJobs() {
  const [status, setStatus] = useState('')
  const { data, loading, error, reload } = useFetch('/hiring/jobs', { status: status || undefined })
  const action = useAction()
  const toggle = (job) => action.run(async () => {
    await api.post(`/hiring/jobs/${job.id}/${job.status === 'active' ? 'close' : 'reopen'}`)
    reload()
  })

  return (
    <div className="container page stack">
      <div className="page-head">
        <div><h1>Manage jobs</h1><p>Jobs posted by your company on Pathwise.</p></div>
        <Link className="btn" to="/employer/jobs/new">Post a job</Link>
      </div>
      <Tabs value={status} onChange={setStatus} tabs={[['', 'All'], ['active', 'Active'], ['closed', 'Closed'], ['expired', 'Expired'], ['pending_review', 'In review']]} />
      <Alert>{error || action.error}</Alert>
      {loading && <Spinner />}
      {data && data.length === 0 && <Empty title="No jobs here" action={<Link className="btn" to="/employer/jobs/new">Post your first job</Link>}>Published jobs appear in search immediately.</Empty>}
      {data?.length > 0 && (
        <div className="card table-wrap">
          <table className="table">
            <thead><tr><th>Title</th><th>Status</th><th>Applications</th><th>Posted</th><th>Expires</th><th><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {data.map((job) => (
                <tr key={job.id}>
                  <td><Link to={`/jobs/${job.id}`}>{job.title}</Link><div className="muted small">{job.location || 'Location not set'}</div></td>
                  <td><Badge tone={TONE[job.status] || 'neutral'}>{job.status.replace('_', ' ')}</Badge></td>
                  <td><Link to={`/employer/applications?job_id=${job.id}`}>{job.application_count}</Link></td>
                  <td>{formatDate(job.published_at)}</td>
                  <td>{formatDate(job.expires_at)}</td>
                  <td>
                    <div className="row">
                      <Link className="btn secondary small" to={`/employer/jobs/${job.id}/edit`}>Edit</Link>
                      {['active', 'closed', 'expired'].includes(job.status) && (
                        <button className="btn secondary small" disabled={action.busy} onClick={() => toggle(job)}>{job.status === 'active' ? 'Close' : 'Reopen'}</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
