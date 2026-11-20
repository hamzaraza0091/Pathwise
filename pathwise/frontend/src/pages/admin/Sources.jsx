import { useState } from 'react'
import api from '../../api'
import { useAction, useFetch } from '../../hooks'
import { Alert, Badge, Field, Spinner } from '../../components/ui'
import { formatDate, timeAgo } from '../../utils'

function SourceCard({ source, onChange }) {
  const [minutes, setMinutes] = useState(source.refresh_minutes)
  const action = useAction()
  const run = (fn) => action.run(async () => { await fn(); onChange() })
  const last = source.last_run
  return (
    <article className="card stack">
      <div className="row between">
        <div>
          <h2 style={{ margin: 0 }}>{source.name}</h2>
          <a className="small" href={source.base_url} target="_blank" rel="noopener noreferrer">{source.base_url}</a>
          {source.terms_url && <> · <a className="small" href={source.terms_url} target="_blank" rel="noopener noreferrer">Terms</a></>}
        </div>
        <div className="row">
          {source.requires_credentials && !source.configured && <Badge tone="warn">Needs API credentials</Badge>}
          <Badge tone={source.enabled ? 'success' : 'muted'}>{source.enabled ? 'Enabled' : 'Disabled'}</Badge>
        </div>
      </div>
      <div className="grid cols-3 small">
        <div><span className="muted">Active jobs</span><br /><strong>{source.active_jobs}</strong></div>
        <div><span className="muted">Last synced</span><br /><strong>{source.last_synced_at ? timeAgo(source.last_synced_at) : 'Never'}</strong></div>
        <div><span className="muted">Last run</span><br /><strong>{last ? `${last.status}: ${last.created} new, ${last.updated} updated, ${last.duplicates} duplicates, ${last.expired} expired` : '—'}</strong></div>
      </div>
      {last?.error && <Alert>{last.error}</Alert>}
      <div className="row">
        <Field label={`Refresh every (minutes, min ${source.min_refresh_minutes ?? 1})`} htmlFor={`rf-${source.id}`}>
          <input id={`rf-${source.id}`} type="number" min={source.min_refresh_minutes ?? 1} value={minutes} onChange={(e) => setMinutes(e.target.value)} style={{ width: 130 }} />
        </Field>
        <button className="btn secondary small" disabled={action.busy || Number(minutes) === source.refresh_minutes} onClick={() => run(() => api.patch(`/admin/sources/${source.id}`, { refresh_minutes: Number(minutes) }))}>Save interval</button>
        <button className="btn secondary small" disabled={action.busy} onClick={() => run(() => api.patch(`/admin/sources/${source.id}`, { enabled: !source.enabled }))}>{source.enabled ? 'Disable' : 'Enable'}</button>
        <button className="btn small" disabled={action.busy || !source.configured} onClick={() => run(() => api.post(`/admin/sources/${source.id}/sync`))}>Sync now</button>
      </div>
      <Alert>{action.error}</Alert>
    </article>
  )
}

export default function AdminSources() {
  const { data, loading, error, reload } = useFetch('/admin/sources')
  return (
    <div className="container page stack">
      <div className="page-head"><div><h1>External sources</h1><p>Authorized APIs and feeds only. Refresh intervals respect each provider's published limits.</p></div></div>
      <Alert kind="info">Sync runs in the background. Refresh this page or open Ingestion to follow progress. Native Pathwise jobs are not listed here.</Alert>
      <Alert>{error}</Alert>
      {loading && <Spinner />}
      {data?.filter((s) => !s.is_native).map((s) => <SourceCard key={s.id} source={s} onChange={reload} />)}
      <p className="muted small">Last page load {formatDate(new Date().toISOString(), true)}</p>
    </div>
  )
}
