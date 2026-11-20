import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { HOME_BY_ROLE, useAuth } from '../../auth'
import { useFetch } from '../../hooks'
import JobCard from '../../components/JobCard'
import { Empty, Spinner } from '../../components/ui'

const STEPS = [
  ['Upload your CV', 'PDF or DOCX. We extract your skills, education and experience and show you exactly what we found so you can correct it.'],
  ['See transparent matches', 'Every job shows a percentage with matched skills, missing skills and concrete suggestions. No black box.'],
  ['Apply where the job lives', 'Jobs from across the web link to the original posting. Jobs posted on Pathwise can be applied to and tracked here.'],
]

export default function Home() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [location, setLocation] = useState('')
  const latest = useFetch('/jobs', { page_size: 6, sort: 'date' })
  const meta = useFetch('/jobs/meta')

  const submit = (event) => {
    event.preventDefault()
    const params = new URLSearchParams()
    if (q) params.set('q', q)
    if (location) params.set('location', location)
    navigate(`/jobs?${params}`)
  }

  return (
    <>
      <section className="hero">
        <div className="container">
          <h1>Find work that fits the skills you actually have.</h1>
          <p>Pathwise gathers jobs from trusted sources and employers, then compares each one with your CV so you can see why it matches and what is missing.</p>
          <form className="hero-search" onSubmit={submit} role="search">
            <label className="sr-only" htmlFor="home-q">Job title, skill or company</label>
            <input id="home-q" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Job title, skill or company" />
            <label className="sr-only" htmlFor="home-loc">Location</label>
            <input id="home-loc" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="City, country or remote" />
            <button className="btn" type="submit">Search jobs</button>
          </form>
          {meta.data && <p style={{ marginTop: '1rem', marginBottom: 0 }}>{meta.data.active_jobs.toLocaleString()} active jobs from {meta.data.sources?.length || 0} sources</p>}
        </div>
      </section>

      <div className="container page stack" style={{ gap: '2rem' }}>
        <section>
          <div className="grid cols-3">
            {STEPS.map(([title, body], i) => (
              <div className="card" key={title}>
                <span className="badge brand">Step {i + 1}</span>
                <h3 style={{ marginTop: '0.6rem' }}>{title}</h3>
                <p className="muted" style={{ margin: 0 }}>{body}</p>
              </div>
            ))}
          </div>
        </section>

        <section>
          <div className="row between" style={{ marginBottom: '0.75rem' }}>
            <h2 style={{ margin: 0 }}>Latest jobs</h2>
            <Link to="/jobs">Browse all jobs →</Link>
          </div>
          {latest.loading && <Spinner />}
          {latest.error && <Empty title="Jobs are unavailable right now">{latest.error}</Empty>}
          {latest.data && latest.data.items.length === 0 && <Empty title="No jobs yet">Jobs will appear here once employers post or sources sync.</Empty>}
          <div className="job-list">{latest.data?.items.map((job) => <JobCard key={job.id} job={job} showMatch={false} />)}</div>
        </section>

        {!user && (
          <section className="card row between">
            <div>
              <h2 style={{ marginBottom: '0.25rem' }}>Ready to see your matches?</h2>
              <p className="muted" style={{ margin: 0 }}>Create a free account, upload your CV, and get recommendations in minutes.</p>
            </div>
            <div className="row">
              <Link className="btn" to="/register">Create account</Link>
              <Link className="btn secondary" to="/register?role=employer">Hire talent</Link>
            </div>
          </section>
        )}
        {user && <Link className="btn" style={{ justifySelf: 'start' }} to={HOME_BY_ROLE[user.role]}>Go to your dashboard</Link>}
      </div>
    </>
  )
}
