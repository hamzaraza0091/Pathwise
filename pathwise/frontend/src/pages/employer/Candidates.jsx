import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import api, { downloadFile } from '../../api'
import { useAction, useFetch } from '../../hooks'
import MatchPanel from '../../components/MatchPanel'
import { Alert, Empty, Field, MatchBadge, Modal, Pagination, Spinner, Tabs } from '../../components/ui'

function Profile({ id, jobId, onClose, onShortlist }) {
  const { data, loading, error } = useFetch(`/hiring/candidates/${id}`, { job_id: jobId || undefined })
  const action = useAction()
  const shortlist = async () => { const ok = await action.run(async () => { await api.post('/hiring/shortlist', { candidate_id: Number(id), job_id: jobId ? Number(jobId) : null }); return true }); if (ok) onShortlist() }
  const cv = () => action.run(() => downloadFile(`/hiring/candidates/${id}/resume`, 'resume'))
  return (
    <Modal title={data?.name || 'Candidate'} onClose={onClose} wide>
      {loading && <Spinner />}
      <Alert>{error || action.error}</Alert>
      {data && (
        <div className="stack">
          <div>
            <strong>{data.headline}</strong>
            <div className="muted small">{[data.location, data.experience_level, data.years_experience != null ? `${data.years_experience} yrs` : null].filter(Boolean).join(' · ')}</div>
            {data.email && <div className="small">{data.email}{data.phone ? ` · ${data.phone}` : ''}</div>}
            {!data.has_applied && <div className="muted small">Contact details are shared once a candidate applies to one of your jobs.</div>}
          </div>
          {data.summary && <p>{data.summary}</p>}
          <div className="row">
            <button className="btn small" onClick={shortlist} disabled={action.busy}>Add to shortlist</button>
            {data.resume_available ? <button className="btn secondary small" onClick={cv}>Download CV</button> : <span className="muted small">CV not shared</span>}
          </div>
          {data.match && <MatchPanel match={data.match} audience="employer" />}
          <section><h3>Skills</h3><div className="tags">{data.data.skills.map((s) => <span key={s.id} className="tag">{s.skill}</span>)}</div></section>
          <section className="grid cols-2">
            <div><h3>Experience</h3>{data.data.experience.map((e) => <div key={e.id} className="small"><strong>{e.title}</strong>{e.company ? ` · ${e.company}` : ''}</div>)}{data.data.experience.length === 0 && <p className="muted small">None listed</p>}</div>
            <div><h3>Education</h3>{data.data.education.map((e) => <div key={e.id} className="small"><strong>{e.degree}</strong>{e.institution ? ` · ${e.institution}` : ''}</div>)}{data.data.education.length === 0 && <p className="muted small">None listed</p>}</div>
          </section>
        </div>
      )}
    </Modal>
  )
}

function Shortlist() {
  const { data, loading, error, reload } = useFetch('/hiring/shortlist')
  const action = useAction()
  const remove = (id) => action.run(async () => { await api.delete(`/hiring/shortlist/${id}`); reload() })
  return (
    <div className="stack">
      <Alert>{error || action.error}</Alert>
      {loading && <Spinner />}
      {data?.length === 0 && <Empty title="Your shortlist is empty">Shortlist candidates from the discovery tab.</Empty>}
      <ul className="list-plain">
        {data?.map((s) => (
          <li key={s.id} className="card row between">
            <span><strong>{s.name}</strong> <span className="muted small">{s.headline} {s.location ? `· ${s.location}` : ''}</span></span>
            <button className="btn ghost small" onClick={() => remove(s.id)}>Remove</button>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function Candidates() {
  const [params, setParams] = useSearchParams()
  const [tab, setTab] = useState('discover')
  const [filters, setFilters] = useState({ q: '', skills: '', location: '', min_years: '', job_id: params.get('job_id') || '', min_match: '' })
  const [applied, setApplied] = useState(filters)
  const [page, setPage] = useState(1)
  const jobs = useFetch('/hiring/jobs', { status: 'active' })
  const { data, loading, error, reload } = useFetch('/hiring/candidates', { ...Object.fromEntries(Object.entries(applied).filter(([, v]) => v !== '')), page }, { enabled: tab === 'discover' })
  const open = params.get('open')
  const set = (key) => (e) => setFilters({ ...filters, [key]: e.target.value })
  const submit = (event) => { event.preventDefault(); setPage(1); setApplied(filters) }
  const close = () => { const next = new URLSearchParams(params); next.delete('open'); setParams(next, { replace: true }) }

  return (
    <div className="container page stack">
      <div className="page-head"><div><h1>Candidates</h1><p>Discover candidates who chose to be visible to employers. Choose a job to see compatibility scores.</p></div></div>
      <Tabs value={tab} onChange={setTab} tabs={[['discover', 'Discover'], ['shortlist', 'Shortlist']]} />
      {tab === 'shortlist' ? <Shortlist /> : (
        <>
          <form className="card stack" onSubmit={submit}>
            <div className="form-grid">
              <Field label="Keywords" htmlFor="cq"><input id="cq" value={filters.q} onChange={set('q')} placeholder="Headline, summary or skill" /></Field>
              <Field label="Skills (all required)" htmlFor="cs"><input id="cs" value={filters.skills} onChange={set('skills')} placeholder="Python, SQL" /></Field>
              <Field label="Location" htmlFor="cl"><input id="cl" value={filters.location} onChange={set('location')} /></Field>
              <Field label="Minimum years" htmlFor="cy"><input id="cy" type="number" min="0" step="0.5" value={filters.min_years} onChange={set('min_years')} /></Field>
              <Field label="Score against job" htmlFor="cj"><select id="cj" value={filters.job_id} onChange={set('job_id')}><option value="">No job selected</option>{jobs.data?.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}</select></Field>
              <Field label="Minimum match %" htmlFor="cm"><input id="cm" type="number" min="0" max="100" disabled={!filters.job_id} value={filters.min_match} onChange={set('min_match')} /></Field>
            </div>
            <div><button className="btn">Search candidates</button></div>
          </form>
          <Alert>{error}</Alert>
          {loading && <Spinner />}
          {data && data.items.length === 0 && <Empty title="No candidates found">Try fewer filters. Only candidates who enabled discoverability appear here.</Empty>}
          <div className="grid cols-2">
            {data?.items.map((c) => (
              <article key={c.id} className="card stack-sm">
                <div className="row between"><div><strong>{c.name}</strong><div className="muted small">{c.headline}</div></div>{c.match != null && <MatchBadge score={c.match} />}</div>
                <div className="muted small">{[c.location, c.experience_level, c.years_experience != null ? `${c.years_experience} yrs` : null].filter(Boolean).join(' · ')}</div>
                <div className="tags">{c.skills.slice(0, 8).map((s) => <span key={s} className="tag">{s}</span>)}</div>
                <div className="row">
                  <button className="btn small" onClick={() => { const next = new URLSearchParams(params); next.set('open', c.id); setParams(next, { replace: true }) }}>View profile</button>
                  {c.shortlisted && <span className="muted small">Shortlisted</span>}
                </div>
              </article>
            ))}
          </div>
          <Pagination page={page} pages={data?.pages} onChange={setPage} />
        </>
      )}
      {open && <Profile id={open} jobId={applied.job_id || params.get('job_id')} onClose={close} onShortlist={() => { reload(); close() }} />}
    </div>
  )
}
