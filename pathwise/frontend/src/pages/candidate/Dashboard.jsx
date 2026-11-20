import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useAuth } from '../../auth'
import { useFetch } from '../../hooks'
import JobCard from '../../components/JobCard'
import { Alert, Badge, Empty, ProgressBar, Spinner, StatusBadge } from '../../components/ui'
import { STATUS_LABELS, formatDate, timeAgo } from '../../utils'

function Stat({ value, label, to }) {
  const body = <div className="stat"><span className="value">{value}</span><span className="label">{label}</span></div>
  return <div className="card">{to ? <Link to={to} style={{ color: 'inherit' }}>{body}</Link> : body}</div>
}

export default function CandidateDashboard() {
  const { user } = useAuth()
  const { data, loading, error } = useFetch('/candidate/dashboard')
  if (loading) return <div className="container page"><Spinner /></div>
  if (error) return <div className="container page"><Alert>{error}</Alert></div>
  const { stats } = data
  const statusData = Object.entries(stats.by_status || {}).map(([status, count]) => ({ name: STATUS_LABELS[status] || status, count }))

  return (
    <div className="container page stack">
      <div className="page-head">
        <div><h1>Hello, {user.full_name.split(' ')[0]}</h1><p>Here is how your job search is going.</p></div>
        <Link className="btn" to="/jobs">Search jobs</Link>
      </div>

      {data.needs_profile && (
        <Alert kind="info">Upload your CV or add your skills so we can calculate real match scores. <Link to="/candidate/resume">Upload CV</Link></Alert>
      )}
      {data.resume?.status === 'processed' && !data.resume.confirmed && (
        <Alert kind="warn">We extracted details from {data.resume.filename}. Please review them for accuracy. <Link to="/candidate/resume">Review extracted data</Link></Alert>
      )}

      <div className="grid cols-4">
        <Stat value={stats.recommended_total} label="Recommended jobs" to="/candidate/recommended" />
        <Stat value={stats.high_match_jobs} label="High-match jobs" to="/candidate/recommended" />
        <Stat value={stats.applied} label="Jobs applied to" to="/candidate/applications" />
        <Stat value={stats.saved} label="Saved jobs" to="/candidate/saved" />
      </div>

      <div className="split">
        <div className="stack">
          <section className="card">
            <div className="row between"><h2>Top recommendations</h2><Link to="/candidate/recommended">See all</Link></div>
            {data.recommended.length === 0 ? (
              <Empty title="No recommendations yet">{data.needs_profile ? 'Add a CV or skills to get started.' : 'New jobs matching your profile will appear here.'}</Empty>
            ) : (
              <div className="job-list">{data.recommended.map((job) => <JobCard key={job.id} job={job} />)}</div>
            )}
          </section>

          <section className="card">
            <div className="row between"><h2>Recent applications</h2><Link to="/candidate/applications">View all</Link></div>
            <p className="muted small">{stats.under_review} awaiting review</p>
            {data.applications.length === 0 ? <Empty title="No applications yet">Apply to jobs posted on Pathwise and track them here.</Empty> : (
              <ul className="list-plain">
                {data.applications.map((a) => (
                  <li key={a.id} className="row between">
                    <span><Link to={`/jobs/${a.job.id}`}>{a.job.title}</Link> <span className="muted small">· {a.job.company_name} · {timeAgo(a.updated_at)}</span></span>
                    <StatusBadge status={a.status} />
                  </li>
                ))}
              </ul>
            )}
            {statusData.length > 0 && (
              <div style={{ height: 180, marginTop: '1rem' }} aria-label="Applications by status chart">
                <ResponsiveContainer>
                  <BarChart data={statusData}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="name" fontSize={12} /><YAxis allowDecimals={false} fontSize={12} /><Tooltip /><Bar dataKey="count" fill="#2557d6" radius={[6, 6, 0, 0]} /></BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </section>
        </div>

        <aside className="stack">
          <section className="card stack-sm">
            <h3>Profile completion</h3>
            <ProgressBar value={data.completion} />
            <div className="row between small"><span>{data.completion}% complete</span><Link to="/candidate/profile">Improve</Link></div>
          </section>
          <section className="card stack-sm">
            <h3>Your CV</h3>
            {data.resume ? (
              <>
                <div>{data.resume.filename}</div>
                <div className="muted small">Uploaded {formatDate(data.resume.uploaded_at)}</div>
                <div className="row"><Badge tone={data.resume.confirmed ? 'success' : 'warn'}>{data.resume.confirmed ? 'Reviewed' : 'Needs review'}</Badge><Link to="/candidate/resume">Manage</Link></div>
              </>
            ) : <Link className="btn small" to="/candidate/resume" style={{ justifySelf: 'start' }}>Upload CV</Link>}
          </section>
          <section className="card stack-sm">
            <h3>Your skills</h3>
            {data.skills.length ? <div className="tags">{data.skills.slice(0, 18).map((s) => <span className="tag" key={s.id}>{s.skill}</span>)}</div> : <p className="muted small" style={{ margin: 0 }}>No skills yet.</p>}
            <Link to="/candidate/profile">Edit skills</Link>
          </section>
          {data.skill_suggestions.length > 0 && (
            <section className="card stack-sm">
              <h3>Skills worth adding</h3>
              <p className="muted small" style={{ margin: 0 }}>Most often missing from your top matches:</p>
              <ul className="list-plain">{data.skill_suggestions.map((s) => <li key={s.skill} className="row between"><span>{s.skill}</span><span className="muted small">{s.jobs} jobs</span></li>)}</ul>
            </section>
          )}
          <section className="card stack-sm">
            <h3>Recent searches</h3>
            {data.search_history.length === 0 ? <p className="muted small" style={{ margin: 0 }}>Your searches will appear here.</p> : (
              <ul className="list-plain">{data.search_history.map((h) => <li key={h.id}><Link to={`/jobs?q=${encodeURIComponent(h.query || '')}`}>{h.query || 'All jobs'}</Link> <span className="muted small">· {h.result_count} results</span></li>)}</ul>
            )}
          </section>
          {/* <section className="card stack-sm">
            <h3>Email notifications</h3>
            <p className="small muted" style={{ margin: 0 }}>{Object.values(data.email_preferences).filter(Boolean).length} of {Object.keys(data.email_preferences).length} alert types on.</p>
            <Link to="/account">Manage email settings</Link>
          </section> */}
        </aside>
      </div>
    </div>
  )
}
