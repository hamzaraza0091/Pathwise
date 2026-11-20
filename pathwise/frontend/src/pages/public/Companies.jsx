import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useDebounced, useFetch } from '../../hooks'
import JobCard from '../../components/JobCard'
import { Alert, Badge, Empty, Pagination, Spinner } from '../../components/ui'

export function Companies() {
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const debounced = useDebounced(q, 300)
  const { data, loading, error } = useFetch('/companies', { q: debounced || undefined, page, page_size: 18 })

  return (
    <div className="container page">
      <div className="page-head">
        <div><h1>Companies</h1><p>Employers hiring on Pathwise</p></div>
        <div style={{ minWidth: 260 }}>
          <label className="sr-only" htmlFor="cq">Search companies</label>
          <input id="cq" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} placeholder="Search companies" />
        </div>
      </div>
      {loading && <Spinner />}
      <Alert>{error}</Alert>
      {data && data.items.length === 0 && <Empty title="No companies found">Employers that post jobs on Pathwise will appear here.</Empty>}
      <div className="grid cols-3">
        {data?.items.map((c) => (
          <Link key={c.id} to={`/companies/${c.id}`} className="card" style={{ color: 'inherit' }}>
            <h3>{c.name} {c.verified && <Badge tone="success">Verified</Badge>}</h3>
            <p className="muted small" style={{ margin: 0 }}>{[c.industry, c.location].filter(Boolean).join(' · ') || 'Company'}</p>
            <p className="small" style={{ margin: '0.5rem 0 0' }}><strong>{c.open_jobs}</strong> open {c.open_jobs === 1 ? 'job' : 'jobs'}</p>
          </Link>
        ))}
      </div>
      {data && <Pagination page={data.page} pages={data.pages} onChange={setPage} />}
    </div>
  )
}

export function CompanyDetail() {
  const { id } = useParams()
  const { data, loading, error } = useFetch(`/companies/${id}`)
  if (loading) return <div className="container page"><Spinner /></div>
  if (error) return <div className="container page"><Alert>{error}</Alert><Link to="/companies">All companies</Link></div>
  return (
    <div className="container page stack">
      <p><Link to="/companies">← All companies</Link></p>
      <div className="card stack-sm">
        <h1>{data.name} {data.verified && <Badge tone="success">Verified</Badge>}</h1>
        <p className="muted small" style={{ margin: 0 }}>{[data.industry, data.size && `${data.size} employees`, data.location].filter(Boolean).join(' · ')}</p>
        {data.website && <a href={data.website} target="_blank" rel="noopener noreferrer nofollow">{data.website}</a>}
        {data.description && <p style={{ whiteSpace: 'pre-wrap', marginTop: '0.5rem' }}>{data.description}</p>}
      </div>
      <h2>Open jobs ({data.jobs.length})</h2>
      {data.jobs.length === 0 && <Empty title="No open jobs right now" />}
      <div className="job-list">{data.jobs.map((job) => <JobCard key={job.id} job={job} showMatch={false} />)}</div>
    </div>
  )
}
