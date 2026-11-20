import { useEffect, useState } from 'react'
import api from '../../api'
import { useAction, useFetch } from '../../hooks'
import { Alert, Field, Spinner } from '../../components/ui'

const DIMENSIONS = [['skills', 'Skills'], ['experience', 'Experience'], ['education', 'Education'], ['location', 'Location and work arrangement'], ['semantic', 'Semantic similarity'], ['preferences', 'Candidate preferences']]

export default function AdminSettings() {
  const { data, loading, error, reload } = useFetch('/admin/settings')
  const [weights, setWeights] = useState(null)
  const [announcement, setAnnouncement] = useState('')
  const [msg, setMsg] = useState('')
  const action = useAction()
  const maint = useAction()
  const audit = useFetch('/admin/audit-logs', { limit: 25 })

  useEffect(() => {
    if (!data) return
    setWeights(Object.fromEntries(DIMENSIONS.map(([k]) => [k, Math.round((data.matching_weights?.weights?.[k] ?? 0) * 100)])))
    setAnnouncement(data.announcement?.text || '')
  }, [data])

  if (loading || !weights) return <div className="container page"><Spinner /></div>
  const total = Object.values(weights).reduce((a, b) => a + Number(b || 0), 0)

  const saveWeights = async (event) => {
    event.preventDefault()
    setMsg('')
    const ok = await action.run(async () => {
      await api.put('/admin/settings/matching_weights', { value: { weights: Object.fromEntries(Object.entries(weights).map(([k, v]) => [k, Number(v) / 100])) } })
      return true
    })
    if (ok) { setMsg('Matching weights saved as a new model version. Existing scores are recomputed on demand.'); reload() }
  }
  const saveAnnouncement = async (event) => {
    event.preventDefault()
    const ok = await action.run(async () => { await api.put('/admin/settings/announcement', { value: { text: announcement } }); return true })
    if (ok) setMsg('Announcement saved.')
  }
  const runMaintenance = async (path, label) => {
    setMsg('')
    const result = await maint.run(async () => (await api.post(`/admin/maintenance/${path}`)).data)
    if (result) setMsg(`${label}: ${JSON.stringify(result)}`)
  }

  return (
    <div className="container page stack" style={{ maxWidth: 900 }}>
      <div className="page-head"><div><h1>System settings</h1><p>Current model {data.matching_weights?.version}</p></div></div>
      <Alert>{error}</Alert>
      <Alert kind="success">{msg}</Alert>
      <form className="card stack" onSubmit={saveWeights}>
        <h2 style={{ margin: 0 }}>Matching weights</h2>
        <p className="muted small" style={{ margin: 0 }}>Percent weight of each dimension in the match score. Must total 100.</p>
        <div className="form-grid">
          {DIMENSIONS.map(([k, label]) => (
            <Field key={k} label={label} htmlFor={`w-${k}`}><input id={`w-${k}`} type="number" min="0" max="100" value={weights[k]} onChange={(e) => setWeights({ ...weights, [k]: e.target.value })} /></Field>
          ))}
        </div>
        <div className="row"><strong style={{ color: total === 100 ? 'var(--success)' : 'var(--danger)' }}>Total {total}%</strong><button className="btn" disabled={action.busy || total !== 100}>Save weights</button></div>
        <Alert>{action.error}</Alert>
      </form>
      <form className="card stack" onSubmit={saveAnnouncement}>
        <h2 style={{ margin: 0 }}>Platform announcement</h2>
        <Field label="Message" htmlFor="an"><textarea id="an" rows={2} maxLength={500} value={announcement} onChange={(e) => setAnnouncement(e.target.value)} /></Field>
        <div><button className="btn secondary" disabled={action.busy}>Save announcement</button></div>
      </form>
      <section className="card stack">
        <h2 style={{ margin: 0 }}>Maintenance</h2>
        <div className="row">
          <button className="btn secondary" disabled={maint.busy} onClick={() => runMaintenance('expire-jobs', 'Expired jobs')}>Expire stale jobs</button>
          <button className="btn secondary" disabled={maint.busy} onClick={() => runMaintenance('reindex', 'Reindexed')}>Rebuild search index</button>
          <button className="btn secondary" disabled={maint.busy} onClick={() => runMaintenance('backup', 'Backup')}>Back up database</button>
        </div>
        <Alert>{maint.error}</Alert>
      </section>
      <section className="card stack-sm">
        <h2 style={{ margin: 0 }}>Recent audit log</h2>
        {audit.data?.length === 0 && <p className="muted small">No entries.</p>}
        <div className="table-wrap"><table className="table"><tbody>{audit.data?.map((a) => <tr key={a.id}><td className="small muted">{new Date(a.created_at).toLocaleString()}</td><td>{a.action}</td><td className="small">{a.entity_type}{a.entity_id ? ` #${a.entity_id}` : ''}</td><td className="small muted">user {a.user_id ?? '—'}</td></tr>)}</tbody></table></div>
      </section>
    </div>
  )
}
