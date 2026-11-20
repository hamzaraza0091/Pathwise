import { Link } from 'react-router-dom'
import { formatSalary, timeAgo } from '../utils'
import { Badge, Highlight, MatchBadge, ModeBadge, TypeLabel } from './ui'

export default function JobCard({ job, onSave, saving, showMatch = true, children }) {
  const salary = formatSalary(job.salary)
  const hl = job.highlight || {}
  return (
    <article className="job-card">
      <div className="row between" style={{ alignItems: 'flex-start' }}>
        <div className="stack-sm">
          <Link className="title" to={`/jobs/${job.id}`}>{hl.title ? <Highlight html={hl.title} /> : job.title}</Link>
          <div className="meta">
            <span>{job.company_name}</span>
            {job.location && <span>📍 {job.location}</span>}
            {salary && <span>💰 {salary}</span>}
            {job.published_at && <span>{timeAgo(job.published_at)}</span>}
          </div>
        </div>
        <div className="row">
          {showMatch && <MatchBadge score={job.match} />}
          {onSave && (
            <button className="btn secondary small" onClick={() => onSave(job)} disabled={saving} aria-pressed={Boolean(job.saved)}>
              {job.saved ? '★ Saved' : '☆ Save'}
            </button>
          )}
        </div>
      </div>
      <div className="tags">
        <ModeBadge mode={job.work_mode} />
        {job.employment_type && <Badge><TypeLabel value={job.employment_type} /></Badge>}
        {job.experience_level && <Badge>{job.experience_level}</Badge>}
        {job.apply_mode === 'external' ? <Badge tone="warn">{job.attribution}</Badge> : <Badge tone="success">Apply on Pathwise</Badge>}
        {job.application_status && <Badge tone="accent">Applied</Badge>}
      </div>
      <p className="excerpt">{hl.snippet ? <Highlight html={hl.snippet} /> : job.excerpt}</p>
      {job.matched_skills?.length > 0 && (
        <div className="tags">
          {job.matched_skills.map((s) => <span key={s} className="tag hit">{s}</span>)}
          {(job.missing_skills || []).map((s) => <span key={s} className="tag miss">missing: {s}</span>)}
        </div>
      )}
      {children}
    </article>
  )
}
