import { useState } from 'react'
import { useFetch } from '../../hooks'
import { Alert, Badge, Empty, Spinner } from '../../components/ui'
import { formatDate } from '../../utils'

const TONE = { success: 'success', partial: 'warn', failed: 'danger', running: 'info' }

function Logs({ runId }) {
  const { data, loading, error } = useFetch(`/admin/sync-runs/${runId}/logs`)
  if (loading) return <Spinner />
  if (error) return <Alert>{error}</Alert>
  if (!data.length) return <p className="muted small" style={{ margin: 0 }}>No log entries for this run.</p>
  return <ul className="list-plain small" style={{ fontFamily: 'ui-monospace, monospace' }}>{data.map((l) => <li key={l.id}><span className="muted">{formatDate(l.created_at, true)}</span> [{l.level}] {l.message}</li>)}</ul>
}

export default function AdminIngestion() {
  const sources = useFetch('/admin/sources')
  const [sourceId, setSourceId] = useState('')
  const { data, loading, error, reload } = useFetch('/admin/sync-runs', { source_id: sourceId || undefined, limit: 50 })
  const [open, setOpen] = useState(null)
  return (
    <div className="container page stack">
      <div className="page-head">
        <div><h1>Ingestion monitor</h1><p>History of job import runs.</p></div>
        <div className="row">
          <label className="sr-only" htmlFor="is">Source</label>
          <select id="is" value={sourceId} onChange={(e) => setSourceId(e.target.value)}><option value="">All sources</option>{sources.data?.filter((s) => !s.is_native).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
          <button className="btn secondary" onClick={reload}>Refresh</button>
        </div>
      </div>
      <Alert>{error}</Alert>
      {loading && <Spinner />}
      {data?.length === 0 && <Empty title="No runs yet">Run a sync from External sources to see results here.</Empty>}
      {data?.length > 0 && (
        <div className="card table-wrap">
          <table className="table">
            <thead><tr><th>Source</th><th>Status</th><th>Fetched</th><th>New</th><th>Updated</th><th>Duplicates</th><th>Rejected</th><th>Expired</th><th>Started</th><th /></tr></thead>
            <tbody>
              {data.map((r) => (
                <>
                  <tr key={r.id}>
                    <td>{r.source}<div className="muted small">{r.triggered_by}</div></td>
                    <td><Badge tone={TONE[r.status] || 'neutral'}>{r.status}</Badge></td>
                    <td>{r.fetched}</td><td>{r.created}</td><td>{r.updated}</td><td>{r.duplicates}</td><td>{r.rejected}</td><td>{r.expired}</td>
                    <td>{formatDate(r.started_at, true)}</td>
                    <td><button className="btn ghost small" aria-expanded={open === r.id} onClick={() => setOpen(open === r.id ? null : r.id)}>Logs</button></td>
                  </tr>
                  {open === r.id && <tr key={`${r.id}-logs`}><td colSpan={10}>{r.error && <Alert>{r.error}</Alert>}<Logs runId={r.id} /></td></tr>}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
