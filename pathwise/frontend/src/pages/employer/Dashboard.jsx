import { Link } from 'react-router-dom'
import { useAuth } from '../../auth'
import { useFetch } from '../../hooks'
import { Alert, Empty, MatchBadge, Spinner, StatusBadge } from '../../components/ui'
import { formatDate, timeAgo } from '../../utils'

export default function EmployerDashboard() {
  const { user } = useAuth()
  const stats = useFetch('/hiring/analytics')
  const apps = useFetch('/hiring/applications', { sort: 'date' })
  const jobs = useFetch('/hiring/jobs')
  const interviews = useFetch('/hiring/interviews')
  const company = useFetch(user.role === 'employer' ? '/employer/company' : null, undefined, { enabled: user.role === 'employer' })

  if (stats.loading) return <div className="container page"><Spinner /></div>
  if (stats.error) return <div className="container page"><Alert>{stats.error}</Alert>{user.role === 'recruiter' && <p>Ask an employer to add you to their company so you can manage hiring.</p>}</div>
  const s = stats.data
  const upcoming = (interviews.data || []).filter((i) => new Date(i.scheduled_at) > new Date() && i.status === 'scheduled').slice(0, 4)

  return (
    <div className="container page stack">
      <div className="page-head">
        <div><h1>Hiring dashboard</h1><p>{company.data?.name || 'Your company'}</p></div>
        {user.role === 'employer' && <Link className="btn" to="/employer/jobs/new">Post a job</Link>}
      </div>
      {company.data && !company.data.description && <Alert kind="info">Complete your company profile so candidates know who you are. <Link to="/employer/company">Edit company</Link></Alert>}
      <div className="grid cols-4">
        <div className="card stat"><span className="value">{s.active_jobs}</span><span className="label">Active jobs</span></div>
        <div className="card stat"><span className="value">{s.total_applications}</span><span className="label">Applications</span></div>
        <div className="card stat"><span className="value">{s.shortlisted}</span><span className="label">Shortlisted</span></div>
        <div className="card stat"><span className="value">{s.interviews}</span><span className="label">Interviews scheduled</span></div>
      </div>
      <div className="split">
        <section className="card">
          <div className="row between"><h2>Latest applications</h2><Link to="/employer/applications">View all</Link></div>
          {apps.data?.length === 0 && <Empty title="No applications yet">Applications to your jobs will appear here with a match score.</Empty>}
          <ul className="list-plain">
            {apps.data?.slice(0, 6).map((a) => (
              <li key={a.id} className="row between">
                <span><Link to={`/employer/applications?open=${a.id}`}>{a.candidate.name}</Link> <span className="muted small">for {a.job.title} · {timeAgo(a.created_at)}</span></span>
                <span className="row"><MatchBadge score={a.match_score} /><StatusBadge status={a.status} /></span>
              </li>
            ))}
          </ul>
        </section>
        <aside className="stack">
          <section className="card stack-sm">
            <h3>Upcoming interviews</h3>
            {upcoming.length === 0 ? <p className="muted small" style={{ margin: 0 }}>None scheduled.</p> : upcoming.map((i) => <div key={i.id} className="small"><strong>{formatDate(i.scheduled_at, true)}</strong><br />{i.candidate} · {i.job_title}</div>)}
            <Link to="/employer/interviews">All interviews</Link>
          </section>
          <section className="card stack-sm">
            <h3>Your jobs</h3>
            {(jobs.data || []).slice(0, 5).map((j) => <div key={j.id} className="row between small"><Link to={`/employer/applications?job_id=${j.id}`}>{j.title}</Link><span className="muted">{j.application_count} apps</span></div>)}
            {jobs.data?.length === 0 && <p className="muted small" style={{ margin: 0 }}>No jobs posted yet.</p>}
          </section>
        </aside>
      </div>
    </div>
  )
}
