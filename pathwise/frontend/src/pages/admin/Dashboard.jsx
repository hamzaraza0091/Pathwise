import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useFetch } from '../../hooks'
import { Alert, Spinner } from '../../components/ui'

export default function AdminDashboard() {
  const { data, loading, error } = useFetch('/admin/analytics')
  if (loading) return <div className="container page"><Spinner /></div>
  if (error) return <div className="container page"><Alert>{error}</Alert></div>
  const jobsByStatus = data.jobs_by_status
  return (
    <div className="container page stack">
      <div className="page-head"><div><h1>Marketplace overview</h1><p>Live platform metrics.</p></div></div>
      {(data.open_reports > 0 || data.pending_review > 0) && (
        <Alert kind="warn">
          {data.open_reports > 0 && <><Link to="/admin/reports">{data.open_reports} open report{data.open_reports > 1 ? 's' : ''}</Link>. </>}
          {data.pending_review > 0 && <><Link to="/admin/jobs?status=pending_review">{data.pending_review} job{data.pending_review > 1 ? 's' : ''} awaiting review</Link>.</>}
        </Alert>
      )}
      <div className="grid cols-4">
        <div className="card stat"><span className="value">{data.total_users}</span><span className="label">Users</span></div>
        <div className="card stat"><span className="value">{data.companies}</span><span className="label">Employer companies</span></div>
        <div className="card stat"><span className="value">{jobsByStatus.active || 0}</span><span className="label">Active jobs</span></div>
        <div className="card stat"><span className="value">{data.applications}</span><span className="label">Native applications</span></div>
      </div>
      <div className="grid cols-2">
        <section className="card">
          <h2>Sign-ups, last 14 days</h2>
          <div style={{ height: 240 }} role="img" aria-label="Line chart of daily sign-ups">
            <ResponsiveContainer><LineChart data={data.signups}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="date" tickFormatter={(d) => d.slice(5)} minTickGap={20} /><YAxis allowDecimals={false} /><Tooltip /><Line type="monotone" dataKey="signups" stroke="#2557d6" strokeWidth={2} /></LineChart></ResponsiveContainer>
          </div>
        </section>
        <section className="card">
          <h2>Active jobs by source</h2>
          {data.jobs_by_source.length === 0 ? <p className="muted">No jobs ingested yet. Enable and sync a source.</p> : (
            <div style={{ height: 240 }} role="img" aria-label="Bar chart of active jobs per source">
              <ResponsiveContainer><BarChart data={data.jobs_by_source}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="source" /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="jobs" fill="#12805c" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer>
            </div>
          )}
        </section>
      </div>
      <div className="grid cols-3">
        <section className="card stack-sm"><h3>Users by role</h3>{Object.entries(data.users_by_role).map(([k, v]) => <div key={k} className="row between small"><span style={{ textTransform: 'capitalize' }}>{k}</span><strong>{v}</strong></div>)}</section>
        <section className="card stack-sm"><h3>Jobs by status</h3>{Object.entries(jobsByStatus).map(([k, v]) => <div key={k} className="row between small"><span>{k.replace('_', ' ')}</span><strong>{v}</strong></div>)}</section>
        <section className="card stack-sm"><h3>Ingestion runs</h3>{Object.keys(data.sync_runs_by_status).length === 0 && <span className="muted small">No runs yet</span>}{Object.entries(data.sync_runs_by_status).map(([k, v]) => <div key={k} className="row between small"><span>{k}</span><strong>{v}</strong></div>)}<div className="row between small"><span>Match scores computed</span><strong>{data.match_scores_computed}</strong></div></section>
      </div>
    </div>
  )
}
