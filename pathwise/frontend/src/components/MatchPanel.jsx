import { ProgressBar } from './ui'
import { MatchBadge } from './ui'

const LABELS = {
  skills: 'Skills',
  experience: 'Experience',
  education: 'Education',
  location: 'Location & work mode',
  semantic: 'CV–job similarity',
  preferences: 'Your preferences',
}

function List({ items, cls }) {
  if (!items?.length) return <span className="muted small">None</span>
  return <div className="tags">{items.map((item) => <span key={item} className={`tag ${cls}`}>{item}</span>)}</div>
}

export default function MatchPanel({ match, audience = 'candidate' }) {
  if (!match) return null
  const employer = audience === 'employer'
  const overall = Math.round(match.overall ?? match.score ?? 0)
  const components = match.components || {}
  return (
    <section className="card stack" aria-label="Match explanation">
      <div className="row between">
        <div>
          <h2 style={{ marginBottom: 0 }}>{employer ? 'Compatibility with this job' : 'Your match'}</h2>
          <p className="muted small" style={{ margin: 0 }}>{employer ? "This percentage estimates how well the candidate's profile fits the job description. It is not a prediction of hiring or interview outcomes." : match.disclaimer}</p>
        </div>
        <MatchBadge score={overall} />
      </div>
      {!employer && <p>{match.summary}</p>}
      <div className="stack-sm">
        {Object.keys(LABELS).map((key) => {
          const part = components[key]
          if (!part) return null
          return (
            <div className="bar-row" key={key}>
              <span>{LABELS[key]}</span>
              <div className="bar" aria-hidden="true"><span style={{ width: `${part.score ?? 0}%` }} /></div>
              <span className="small muted">{part.applicable ? `${Math.round(part.score)}% · ${Math.round((part.effective_weight || 0) * 100)}% weight` : 'Not applicable'}</span>
            </div>
          )
        })}
      </div>
      <div className="grid cols-2">
        <div><h3>{employer ? 'Required skills they have' : 'Matched skills'}</h3><List items={match.matched_skills} cls="hit" /></div>
        <div><h3>{employer ? 'Required skills not found' : 'Missing required skills'}</h3><List items={match.missing_required_skills} cls="miss" /></div>
        <div><h3>{employer ? 'Preferred skills they have' : 'Preferred skills you have'}</h3><List items={match.matched_preferred_skills} cls="hit" /></div>
        <div><h3>{employer ? 'Preferred skills not found' : 'Preferred skills to add'}</h3><List items={match.missing_preferred_skills} cls="miss" /></div>
      </div>
      {match.candidate_skills_not_requested?.length > 0 && (
        <div><h3>{employer ? 'Other skills' : 'Other skills you bring'}</h3><List items={match.candidate_skills_not_requested} cls="extra" /></div>
      )}
      <div className="grid cols-3">
        <div className="card flat">
          <h3>Experience</h3>
          <p className="small muted" style={{ margin: 0 }}>
            {employer ? 'Candidate' : 'You'}: {match.experience?.candidate_years ?? 0} yrs ({match.experience?.candidate_level || 'n/a'})<br />
            Role: {match.experience?.required_years ? `${match.experience.required_years} yrs` : 'not stated'} ({match.experience?.job_level || 'n/a'})
          </p>
        </div>
        <div className="card flat">
          <h3>Education</h3>
          <p className="small muted" style={{ margin: 0 }}>{match.education?.required ? `Role asks for: ${match.education.required.replace('_', ' ')}` : 'No education requirement stated'}</p>
        </div>
        <div className="card flat">
          <h3>Location</h3>
          <p className="small muted" style={{ margin: 0 }}>Work mode: {match.location?.mode || 'not stated'}{match.location?.note ? ` — ${match.location.note}` : ''}</p>
        </div>
      </div>
      {!employer && match.suggestions?.length > 0 && (
        <div>
          <h3>How to improve your CV for this role</h3>
          <ul className="list-bullets">{match.suggestions.map((s) => <li key={s}>{s}</li>)}</ul>
        </div>
      )}
      <ProgressBar value={overall} />
    </section>
  )
}
