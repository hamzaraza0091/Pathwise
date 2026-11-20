import { useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../api'
import { useAction, useFetch } from '../../hooks'
import { Alert, Badge, Empty, Pagination, Spinner, Tabs } from '../../components/ui'
import { timeAgo } from '../../utils'

export default function AdminReports() {
  const [status, setStatus] = useState('open')
  const [page, setPage] = useState(1)
  const { data, loading, error, reload } = useFetch('/admin/reports', { status: status || undefined, page, page_size: 20 })
  const action = useAction()
  const resolve = (r, act) => action.run(async () => { await api.post(`/admin/reports/${r.id}/resolve`, { action: act }); reload() })
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1
  return (
    <div className="container page stack">
      <div className="page-head"><div><h1>Reports and moderation</h1><p>Jobs flagged by candidates.</p></div></div>
      <Tabs value={status} onChange={(v) => { setStatus(v); setPage(1) }} tabs={[['open', 'Open'], ['resolved', 'Resolved'], ['dismissed', 'Dismissed'], ['', 'All']]} />
      <Alert>{error || action.error}</Alert>
      {loading && <Spinner />}
      {data?.items.length === 0 && <Empty title="Nothing to review" />}
      <div className="stack">
        {data?.items.map((r) => (
          <article key={r.id} className="card stack-sm">
            <div className="row between">
              <div><Link to={`/jobs/${r.job_id}`}><strong>{r.job_title || `Job #${r.job_id}`}</strong></Link> <span className="muted small">{r.company_name}</span></div>
              <div className="row"><Badge tone="warn">{r.reason}</Badge><Badge tone={r.status === 'open' ? 'danger' : 'muted'}>{r.status}</Badge></div>
            </div>
            {r.details && <p style={{ margin: 0 }}>{r.details}</p>}
            <div className="muted small">Reported {timeAgo(r.created_at)} by {r.reporter || 'unknown'}{r.resolution ? ` · ${r.resolution}` : ''}</div>
            {r.status === 'open' && (
              <div className="row">
                <button className="btn small" disabled={action.busy} onClick={() => resolve(r, 'remove_job')}>Remove job</button>
                <button className="btn secondary small" disabled={action.busy} onClick={() => resolve(r, 'dismiss')}>Dismiss</button>
              </div>
            )}
          </article>
        ))}
      </div>
      <Pagination page={page} pages={pages} onChange={setPage} />
    </div>
  )
}
