import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks'
import { Alert, Badge, Empty, Spinner } from '../../components/ui'
import { formatDate } from '../../utils'

export default function Interviews() {
  const { data, loading, error } = useFetch('/hiring/interviews')
  const now = new Date()
  const upcoming = (data || []).filter((i) => new Date(i.scheduled_at) >= now)
  const past = (data || []).filter((i) => new Date(i.scheduled_at) < now).reverse()

  const table = (rows) => (
    <div className="card table-wrap">
      <table className="table">
        <thead><tr><th>When</th><th>Candidate</th><th>Job</th><th>Format</th><th>Where</th><th>Status</th></tr></thead>
        <tbody>
          {rows.map((i) => (
            <tr key={i.id}>
              <td>{formatDate(i.scheduled_at, true)}<div className="muted small">{i.duration_minutes} min</div></td>
              <td><Link to={`/employer/applications?open=${i.application_id}`}>{i.candidate}</Link></td>
              <td>{i.job_title}</td>
              <td>{i.mode}</td>
              <td>{/^https?:\/\//.test(i.location_or_link || '') ? <a href={i.location_or_link} target="_blank" rel="noopener noreferrer">Open link</a> : i.location_or_link || '—'}</td>
              <td><Badge tone={i.status === 'scheduled' ? 'info' : 'muted'}>{i.status}</Badge></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )

  return (
    <div className="container page stack">
      <div className="page-head"><div><h1>Interviews</h1><p>Schedule interviews from an application to invite candidates.</p></div><Link className="btn secondary" to="/employer/applications?status=shortlisted">Shortlisted applicants</Link></div>
      <Alert>{error}</Alert>
      {loading && <Spinner />}
      {data && data.length === 0 && <Empty title="No interviews scheduled">Open a shortlisted application and choose Schedule interview.</Empty>}
      {upcoming.length > 0 && <section className="stack-sm"><h2>Upcoming</h2>{table(upcoming)}</section>}
      {past.length > 0 && <section className="stack-sm"><h2>Past</h2>{table(past)}</section>}
    </div>
  )
}
