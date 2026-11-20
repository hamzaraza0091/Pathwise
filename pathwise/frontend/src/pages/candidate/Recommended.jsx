import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../api'
import { useAction, useFetch } from '../../hooks'
import JobCard from '../../components/JobCard'
import { Alert, Empty, Pagination, Spinner } from '../../components/ui'
import { LEVELS, MODE_LABELS, TYPE_LABELS, toParams } from '../../utils'

export default function Recommended() {
  const [filters, setFilters] = useState({ min_score: '', location: '', employment_type: '', experience_level: '', work_mode: '', page: 1 })
  const params = useMemo(() => ({ ...toParams(filters), page_size: 12 }), [filters])
  const { data, loading, error, setData } = useFetch('/candidate/recommendations', params)
  const action = useAction()
  const set = (key) => (e) => setFilters({ ...filters, [key]: e.target.value, page: 1 })

  const toggleSave = (job) =>
    action.run(async () => {
      if (job.saved) await api.delete(`/jobs/${job.id}/save`)
      else await api.post(`/jobs/${job.id}/save`)
      setData((prev) => ({ ...prev, items: prev.items.map((j) => (j.id === job.id ? { ...j, saved: !job.saved } : j)) }))
    })

  return (
    <div className="container page stack">
      <div className="page-head"><div><h1>Recommended for you</h1><p>Ranked by how well each job fits your CV and preferences.</p></div></div>
      <form className="card form-grid" style={{ gridTemplateColumns: 'repeat(5, minmax(0, 1fr))' }} onSubmit={(e) => e.preventDefault()} aria-label="Recommendation filters">
        <div className="field"><label htmlFor="rs">Minimum match</label>
          <select id="rs" value={filters.min_score} onChange={set('min_score')}><option value="">Any</option><option value="80">80%+</option><option value="60">60%+</option><option value="40">40%+</option></select></div>
        <div className="field"><label htmlFor="rl">Location</label><input id="rl" value={filters.location} onChange={set('location')} placeholder="City or country" /></div>
        <div className="field"><label htmlFor="rm">Work mode</label>
          <select id="rm" value={filters.work_mode} onChange={set('work_mode')}><option value="">Any</option>{Object.entries(MODE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
        <div className="field"><label htmlFor="rt">Employment type</label>
          <select id="rt" value={filters.employment_type} onChange={set('employment_type')}><option value="">Any</option>{Object.entries(TYPE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
        <div className="field"><label htmlFor="re">Experience level</label>
          <select id="re" value={filters.experience_level} onChange={set('experience_level')}><option value="">Any</option>{LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}</select></div>
      </form>
      <Alert>{action.error || error}</Alert>
      {loading && <Spinner label="Ranking jobs for you…" />}
      {data?.needs_profile && <Alert kind="info">Add skills or upload a CV to get accurate recommendations. <Link to="/candidate/resume">Upload CV</Link></Alert>}
      {data && !loading && data.items.length === 0 && !data.needs_profile && <Empty title="No recommendations match these filters">Try lowering the minimum match or clearing filters.</Empty>}
      <div className="job-list">{!loading && data?.items.map((job) => <JobCard key={job.id} job={job} onSave={toggleSave} saving={action.busy}><p className="small muted" style={{ margin: 0 }}>{job.match_summary}</p></JobCard>)}</div>
      {data && <Pagination page={data.page} pages={data.pages} onChange={(page) => setFilters({ ...filters, page })} />}
    </div>
  )
}
