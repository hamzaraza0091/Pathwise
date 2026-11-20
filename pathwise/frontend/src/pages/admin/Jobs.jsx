import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import api from '../../api'
import { useAction, useDebounced, useFetch } from '../../hooks'
import { Alert, Badge, Empty, Pagination, Spinner } from '../../components/ui'
import { formatDate } from '../../utils'

const TONE = { active: 'success', closed: 'muted', expired: 'warn', pending_review: 'warn', removed: 'danger' }

export default function AdminJobs() {
  const [params] = useSearchParams()
  const [q, setQ] = useState('')
  const [status, setStatus] = useState(params.get('status') || '')
  const [source, setSource] = useState('')
  const [page, setPage] = useState(1)
  const dq = useDebounced(q)
  const meta = useFetch('/jobs/meta')
  const { data, loading, error, reload } = useFetch('/admin/jobs', { q: dq || undefined, status: status || undefined, source: source || undefined, page, page_size: 20 })
  const action = useAction()
  const setJobStatus = (job, next) => action.run(async () => { await api.post(`/admin/jobs/${job.id}/status`, { status: next }); reload() })
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1

  return (
    <div className="container page stack">
      <div className="page-head"><div><h1>Job management</h1><p>{data ? `${data.total} jobs` : 'Review, approve or remove postings.'}</p></div></div>
      <div className="card row">
        <div style={{ flex: 1, minWidth: 220 }}><label className="sr-only" htmlFor="jq">Search jobs</label><input id="jq" type="search" placeholder="Search title or company" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} /></div>
        <label className="sr-only" htmlFor="js">Status</label>
        <select id="js" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} style={{ width: 170 }}><option value="">All statuses</option>{Object.keys(TONE).map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}</select>
        <label className="sr-only" htmlFor="jsrc">Source</label>
        <select id="jsrc" value={source} onChange={(e) => { setSource(e.target.value); setPage(1) }} style={{ width: 170 }}><option value="">All sources</option>{meta.data?.sources.map((s) => <option key={s.key} value={s.key}>{s.name}</option>)}</select>
      </div>
      <Alert>{error || action.error}</Alert>
      {loading && <Spinner />}
      {data?.items.length === 0 && <Empty title="No jobs match these filters" />}
      {data?.items.length > 0 && (
        <div className="card table-wrap">
          <table className="table">
            <thead><tr><th>Job</th><th>Source</th><th>Status</th><th>Posted</th><th /></tr></thead>
            <tbody>
              {data.items.map((j) => (
                <tr key={j.id}>
                  <td><Link to={`/jobs/${j.id}`}>{j.title}</Link><div className="muted small">{j.company_name}</div></td>
                  <td>{j.source.name}</td>
                  <td><Badge tone={TONE[j.status] || 'neutral'}>{j.status.replace('_', ' ')}</Badge></td>
                  <td>{formatDate(j.published_at)}</td>
                  <td>
                    <div className="row">
                      {j.status === 'pending_review' && <button className="btn small" disabled={action.busy} onClick={() => setJobStatus(j, 'active')}>Approve</button>}
                      {['active', 'pending_review', 'closed'].includes(j.status) && j.status !== 'removed' && <button className="btn secondary small" disabled={action.busy} onClick={() => setJobStatus(j, 'removed')}>Remove</button>}
                      {j.status === 'removed' && <button className="btn secondary small" disabled={action.busy} onClick={() => setJobStatus(j, 'active')}>Restore</button>}
                    </div>
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
