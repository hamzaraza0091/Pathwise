import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import api, { errorMessage } from '../../api'
import { useAuth } from '../../auth'
import { useAction, useFetch } from '../../hooks'
import MatchPanel from '../../components/MatchPanel'
import { Alert, Badge, Field, Modal, ModeBadge, Spinner, StatusBadge, TypeLabel } from '../../components/ui'
import { formatDate, formatSalary } from '../../utils'

const REASONS = [['scam', 'Scam or fraud'], ['misleading', 'Misleading'], ['discriminatory', 'Discriminatory'], ['duplicate', 'Duplicate'], ['expired', 'No longer available'], ['other', 'Other']]

export default function JobDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const navigate = useNavigate()
  const { data: job, loading, error, reload } = useFetch(`/jobs/${id}`)
  const isCandidate = user?.role === 'candidate'
  const [applyOpen, setApplyOpen] = useState(false)
  const [reportOpen, setReportOpen] = useState(false)
  const [cover, setCover] = useState('')
  const [reason, setReason] = useState('scam')
  const [details, setDetails] = useState('')
  const [notice, setNotice] = useState('')
  const action = useAction()

  if (loading) return <div className="container page"><Spinner /></div>
  if (error) return <div className="container page"><Alert>{error}</Alert><Link to="/jobs">Back to jobs</Link></div>
  if (!job) return null

  const salary = formatSalary(job.salary)
  const external = job.apply_mode === 'external'
  const closed = job.status !== 'active'

  const requireCandidate = () => {
    if (!user) {
      navigate('/login', { state: { from: `/jobs/${job.id}` } })
      return false
    }
    return isCandidate
  }

  const toggleSave = () =>
    requireCandidate() &&
    action.run(async () => {
      if (job.saved) await api.delete(`/jobs/${job.id}/save`)
      else await api.post(`/jobs/${job.id}/save`)
      await reload()
    })

  const submitApplication = async (event) => {
    event.preventDefault()
    const result = await action.run(() => api.post(`/jobs/${job.id}/apply`, { cover_letter: cover || null }))
    if (result) {
      setApplyOpen(false)
      setNotice('Application submitted. You will be notified when the employer updates its status.')
      reload()
    }
  }

  const submitReport = async (event) => {
    event.preventDefault()
    const result = await action.run(() => api.post(`/jobs/${job.id}/report`, { reason, details: details || null }))
    if (result) {
      setReportOpen(false)
      setNotice('Thanks. Our team will review this job.')
    }
  }

  return (
    <div className="container page">
      <p><Link to="/jobs">← Back to jobs</Link></p>
      <div className="split">
        <div className="stack">
          <article className="card stack">
            <div>
              <h1>{job.title}</h1>
              <p className="muted" style={{ margin: 0 }}>
                {job.company?.id && !external ? <Link to={`/companies/${job.company.id}`}>{job.company_name}</Link> : job.company_name}
                {job.location ? ` · ${job.location}` : ''}
              </p>
            </div>
            <div className="tags">
              <ModeBadge mode={job.work_mode} />
              {job.employment_type && <Badge><TypeLabel value={job.employment_type} /></Badge>}
              {job.experience_level && <Badge>{job.experience_level}</Badge>}
              {job.category && <Badge>{job.category}</Badge>}
              {salary && <Badge tone="success">{salary}</Badge>}
              {closed && <Badge tone="danger">No longer accepting applications</Badge>}
            </div>
            {external && (
              <Alert kind="info">
                {job.attribution}. Applications are completed on the original website; Pathwise does not submit them for you.
              </Alert>
            )}
            <Alert kind="success">{notice}</Alert>
            <Alert>{action.error}</Alert>
            <div className="row">
              {external ? (
                <a className="btn" href={job.apply_url || job.original_url} target="_blank" rel="noopener noreferrer nofollow">Apply on Original Website ↗</a>
              ) : job.application_status ? (
                <span className="row"><StatusBadge status={job.application_status} /><Link to="/candidate/applications">Track application</Link></span>
              ) : (
                <button className="btn" disabled={closed || (user && !isCandidate)} onClick={() => requireCandidate() && setApplyOpen(true)}>Apply now</button>
              )}
              <button className="btn secondary" onClick={toggleSave} disabled={action.busy || (user && !isCandidate)}>{job.saved ? '★ Saved' : '☆ Save job'}</button>
              {user && <button className="btn ghost" onClick={() => setReportOpen(true)}>Report job</button>}
            </div>
            {!user && <p className="muted small" style={{ margin: 0 }}><Link to="/login" state={{ from: `/jobs/${job.id}` }}>Sign in</Link> as a candidate to save this job, apply, and see your match.</p>}
          </article>

          <article className="card">
            <h2>Job description</h2>
            <div style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{job.description}</div>
          </article>

          {isCandidate && job.match_details && <MatchPanel match={job.match_details} />}
          {isCandidate && !job.match_details && (
            <Alert kind="info">Upload your CV or add skills to your profile to see how well you match this job. <Link to="/candidate/resume">Upload CV</Link></Alert>
          )}
        </div>

        <aside className="stack">
          <div className="card stack-sm">
            <h3>Required skills</h3>
            <div className="tags">{job.skills.required.length ? job.skills.required.map((s) => <span className="tag" key={s}>{s}</span>) : <span className="muted small">Not specified</span>}</div>
            {job.skills.preferred.length > 0 && (<><h3 style={{ marginTop: '0.75rem' }}>Preferred skills</h3><div className="tags">{job.skills.preferred.map((s) => <span className="tag" key={s}>{s}</span>)}</div></>)}
          </div>
          <div className="card stack-sm small">
            <h3>Job details</h3>
            <div>Posted: {formatDate(job.published_at)}</div>
            {job.expires_at && <div>Expires: {formatDate(job.expires_at)}</div>}
            <div>Source: {job.source.name}</div>
            {external && <div>First imported: {formatDate(job.first_imported_at)}</div>}
            {external && job.original_url && <a href={job.original_url} target="_blank" rel="noopener noreferrer nofollow">View original posting ↗</a>}
          </div>
        </aside>
      </div>

      {applyOpen && (
        <Modal title={`Apply to ${job.title}`} onClose={() => setApplyOpen(false)}>
          <form className="stack" onSubmit={submitApplication}>
            <p className="muted small" style={{ margin: 0 }}>Your active CV and match score will be shared with {job.company_name}.</p>
            <Field label="Cover letter (optional)" htmlFor="cover"><textarea id="cover" value={cover} maxLength={5000} onChange={(e) => setCover(e.target.value)} /></Field>
            <Alert>{action.error}</Alert>
            <div className="row"><button className="btn" disabled={action.busy}>{action.busy ? 'Submitting…' : 'Submit application'}</button><button type="button" className="btn secondary" onClick={() => setApplyOpen(false)}>Cancel</button></div>
          </form>
        </Modal>
      )}
      {reportOpen && (
        <Modal title="Report this job" onClose={() => setReportOpen(false)}>
          <form className="stack" onSubmit={submitReport}>
            <Field label="Reason" htmlFor="reason"><select id="reason" value={reason} onChange={(e) => setReason(e.target.value)}>{REASONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
            <Field label="Details (optional)" htmlFor="details"><textarea id="details" value={details} maxLength={1000} onChange={(e) => setDetails(e.target.value)} /></Field>
            <Alert>{action.error}</Alert>
            <div className="row"><button className="btn danger" disabled={action.busy}>Submit report</button><button type="button" className="btn secondary" onClick={() => setReportOpen(false)}>Cancel</button></div>
          </form>
        </Modal>
      )}
    </div>
  )
}
