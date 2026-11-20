import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import api, { errorMessage } from '../../api'
import { useAuth } from '../../auth'
import { useDebounced, useFetch } from '../../hooks'
import JobCard from '../../components/JobCard'
import { Alert, Empty, Pagination, Spinner } from '../../components/ui'
import { LEVELS, MODE_LABELS, TYPE_LABELS, toParams } from '../../utils'

const LIST_KEYS = ['work_mode', 'employment_type', 'experience_level']
const TEXT_KEYS = ['q', 'location', 'company', 'skills', 'category', 'source', 'salary_min', 'posted_within_days', 'min_match', 'sort']

function readFilters(params) {
  const filters = { page: Number(params.get('page') || 1) }
  TEXT_KEYS.forEach((key) => { filters[key] = params.get(key) || '' })
  LIST_KEYS.forEach((key) => { filters[key] = (params.get(key) || '').split(',').filter(Boolean) })
  return filters
}

function toggle(list, value) {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value]
}

export default function Jobs() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const filters = useMemo(() => readFilters(params), [params])
  const [draftQ, setDraftQ] = useState(filters.q)
  const [suggestions, setSuggestions] = useState([])
  const [showSuggest, setShowSuggest] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [savingId, setSavingId] = useState(null)
  const meta = useFetch('/jobs/meta')
  const isCandidate = user?.role === 'candidate'

  const query = useMemo(() => {
    const { page, sort, ...rest } = filters
    return { ...toParams(rest), page, sort: sort || undefined, page_size: 15 }
  }, [filters])
  const results = useFetch('/jobs', query)
  const debouncedQ = useDebounced(draftQ, 200)

  useEffect(() => setDraftQ(filters.q), [filters.q])

  useEffect(() => {
    if (debouncedQ.trim().length < 2) {
      setSuggestions([])
      return undefined
    }
    let cancelled = false
    api.get('/jobs/suggestions', { params: { q: debouncedQ } }).then(({ data }) => !cancelled && setSuggestions(data)).catch(() => {})
    return () => { cancelled = true }
  }, [debouncedQ])

  const update = (patch, resetPage = true) => {
    const next = { ...filters, ...patch }
    if (resetPage) next.page = 1
    const out = toParams({ ...next, page: next.page > 1 ? next.page : '' })
    setParams(out, { replace: false })
  }

  const clear = () => setParams({})

  const onSave = async (job) => {
    if (!isCandidate) {
      navigate('/login', { state: { from: '/jobs' } })
      return
    }
    setSavingId(job.id)
    setSaveError('')
    try {
      if (job.saved) await api.delete(`/jobs/${job.id}/save`)
      else await api.post(`/jobs/${job.id}/save`)
      results.setData((prev) => ({ ...prev, items: prev.items.map((j) => (j.id === job.id ? { ...j, saved: !job.saved } : j)) }))
    } catch (err) {
      setSaveError(errorMessage(err))
    } finally {
      setSavingId(null)
    }
  }

  const activeCount = Object.entries(filters).filter(([k, v]) => k !== 'page' && k !== 'sort' && (Array.isArray(v) ? v.length : v)).length

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1>Find jobs</h1>
          <p>{results.data ? `${results.data.total.toLocaleString()} jobs found` : 'Searching…'}</p>
        </div>
      </div>
      <div className="sidebar-layout">
        <aside className="card filters" aria-label="Filters">
          <div className="row between"><h2 style={{ margin: 0 }}>Filters</h2>{activeCount > 0 && <button className="btn ghost small" onClick={clear}>Clear all ({activeCount})</button>}</div>
          <div className="field">
            <label htmlFor="f-loc">Location</label>
            <input id="f-loc" defaultValue={filters.location} key={`loc-${filters.location}`} onBlur={(e) => e.target.value !== filters.location && update({ location: e.target.value })} onKeyDown={(e) => e.key === 'Enter' && update({ location: e.target.value })} placeholder="City or country" />
          </div>
          <div className="field">
            <label htmlFor="f-company">Company</label>
            <input id="f-company" defaultValue={filters.company} key={`co-${filters.company}`} onBlur={(e) => e.target.value !== filters.company && update({ company: e.target.value })} onKeyDown={(e) => e.key === 'Enter' && update({ company: e.target.value })} />
          </div>
          <div className="field">
            <label htmlFor="f-skills">Skills (all required)</label>
            <input id="f-skills" defaultValue={filters.skills} key={`sk-${filters.skills}`} onBlur={(e) => e.target.value !== filters.skills && update({ skills: e.target.value })} onKeyDown={(e) => e.key === 'Enter' && update({ skills: e.target.value })} placeholder="python, sql" />
          </div>
          <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
            <legend className="small" style={{ fontWeight: 600, marginBottom: 6 }}>Work arrangement</legend>
            <div className="chips">
              {Object.entries(MODE_LABELS).map(([value, label]) => (
                <button key={value} className="chip" aria-pressed={filters.work_mode.includes(value)} onClick={() => update({ work_mode: toggle(filters.work_mode, value) })}>{label}</button>
              ))}
            </div>
          </fieldset>
          <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
            <legend className="small" style={{ fontWeight: 600, marginBottom: 6 }}>Employment type</legend>
            <div className="chips">
              {Object.entries(TYPE_LABELS).map(([value, label]) => (
                <button key={value} className="chip" aria-pressed={filters.employment_type.includes(value)} onClick={() => update({ employment_type: toggle(filters.employment_type, value) })}>{label}</button>
              ))}
            </div>
          </fieldset>
          <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
            <legend className="small" style={{ fontWeight: 600, marginBottom: 6 }}>Experience level</legend>
            <div className="chips">
              {LEVELS.map((value) => (
                <button key={value} className="chip" aria-pressed={filters.experience_level.includes(value)} onClick={() => update({ experience_level: toggle(filters.experience_level, value) })}>{value}</button>
              ))}
            </div>
          </fieldset>
          <div className="field">
            <label htmlFor="f-cat">Category</label>
            <select id="f-cat" value={filters.category} onChange={(e) => update({ category: e.target.value })}>
              <option value="">All categories</option>
              {meta.data?.categories.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="f-source">Source</label>
            <select id="f-source" value={filters.source} onChange={(e) => update({ source: e.target.value })}>
              <option value="">All sources</option>
              {meta.data?.sources.map((s) => <option key={s.key} value={s.key}>{s.name}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="f-date">Posted</label>
            <select id="f-date" value={filters.posted_within_days} onChange={(e) => update({ posted_within_days: e.target.value })}>
              <option value="">Any time</option>
              <option value="1">Last 24 hours</option>
              <option value="7">Last 7 days</option>
              <option value="30">Last 30 days</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="f-sal">Minimum salary (yearly)</label>
            <input id="f-sal" type="number" min="0" defaultValue={filters.salary_min} key={`sal-${filters.salary_min}`} onBlur={(e) => e.target.value !== filters.salary_min && update({ salary_min: e.target.value })} />
          </div>
          {isCandidate && (
            <div className="field">
              <label htmlFor="f-match">Minimum match: {filters.min_match || 0}%</label>
              <input id="f-match" type="range" min="0" max="100" step="10" value={filters.min_match || 0} onChange={(e) => update({ min_match: Number(e.target.value) || '' })} />
            </div>
          )}
        </aside>

        <section className="stack" aria-live="polite">
          <form className="card row" role="search" onSubmit={(e) => { e.preventDefault(); setShowSuggest(false); update({ q: draftQ }) }}>
            <div className="relative" style={{ flex: 1, minWidth: 200 }}>
              <label className="sr-only" htmlFor="q">Search jobs</label>
              <input id="q" value={draftQ} autoComplete="off" onChange={(e) => { setDraftQ(e.target.value); setShowSuggest(true) }} onBlur={() => setTimeout(() => setShowSuggest(false), 150)} placeholder="Job title, keywords or company" />
              {showSuggest && suggestions.length > 0 && (
                <div className="suggest" role="listbox">
                  {suggestions.map((s) => (
                    <button type="button" role="option" aria-selected="false" key={`${s.type}-${s.value}`} onMouseDown={() => { setDraftQ(s.value); setShowSuggest(false); update({ q: s.value }) }}>
                      <span>{s.value}</span><span className="muted small">{s.type}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button className="btn" type="submit">Search</button>
            <div className="field" style={{ minWidth: 150 }}>
              <label className="sr-only" htmlFor="sort">Sort by</label>
              <select id="sort" value={filters.sort || ''} onChange={(e) => update({ sort: e.target.value })}>
                <option value="">Best match to search</option>
                <option value="date">Newest</option>
                <option value="salary">Highest salary</option>
                {isCandidate && <option value="match">Best CV match</option>}
              </select>
            </div>
          </form>

          <Alert>{saveError}</Alert>
          {results.loading && <Spinner label="Searching jobs…" />}
          {results.error && <Alert>{results.error}</Alert>}
          {!results.loading && results.data?.items.length === 0 && (
            <Empty title="No jobs match your search" action={activeCount > 0 && <button className="btn secondary" onClick={clear}>Clear filters</button>}>Try fewer filters or different keywords.</Empty>
          )}
          {!results.loading && !isCandidate && results.data?.items.length > 0 && !user && (
            <Alert kind="info">Sign in as a candidate and upload your CV to see a match percentage on every job.</Alert>
          )}
          <div className="job-list">
            {!results.loading && results.data?.items.map((job) => <JobCard key={job.id} job={job} onSave={onSave} saving={savingId === job.id} showMatch={isCandidate} />)}
          </div>
          {results.data && <Pagination page={results.data.page} pages={results.data.pages} onChange={(page) => { update({ page }, false); window.scrollTo({ top: 0 }) }} />}
        </section>
      </div>
    </div>
  )
}
