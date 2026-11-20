import { useCallback, useEffect, useRef, useState } from 'react'
import api, { downloadFile, errorMessage } from '../../api'
import { useAction, useFetch } from '../../hooks'
import { Alert, Badge, Empty, Modal, Spinner } from '../../components/ui'
import { formatDate } from '../../utils'

const PENDING = ['uploaded', 'processing']
const MAX_MB = 5

function StatusPill({ resume }) {
  const map = { uploaded: ['info', 'Queued'], processing: ['info', 'Reading your CV…'], processed: ['success', 'Processed'], failed: ['danger', 'Could not read'] }
  const [tone, label] = map[resume.status] || ['neutral', resume.status]
  return <Badge tone={tone}>{label}</Badge>
}

function Review({ id, onClose, onChanged }) {
  const { data, loading, error, reload } = useFetch(`/candidate/resumes/${id}`)
  const action = useAction()
  const confirm = async () => {
    const ok = await action.run(async () => { await api.post(`/candidate/resumes/${id}/confirm`); return true })
    if (ok) { await reload(); onChanged() }
  }
  const x = data?.extracted
  const evidence = data?.evidence || {}
  return (
    <Modal title="Review extracted information" onClose={onClose} wide>
      {loading && <Spinner />}
      <Alert>{error || action.error}</Alert>
      {x && (
        <div className="stack">
          <Alert kind="info">This is what we found in your CV. Nothing is invented: every item comes from your document. Edit anything that is wrong on your <a href="/candidate/profile">profile page</a>; your corrections are used for matching.</Alert>
          <div className="grid cols-2">
            <div className="card flat"><h3>Candidate</h3><div>{x.name || '—'}</div><div className="muted small">{x.email}{x.phone ? ` · ${x.phone}` : ''}{x.location ? ` · ${x.location}` : ''}</div><div className="small" style={{ marginTop: 6 }}>{x.experience_level} · {x.years_experience ?? 0} years of experience</div></div>
            <div className="card flat"><h3>Method</h3><p className="small muted" style={{ margin: 0 }}>Extracted with {data.method === 'rules' ? 'rule-based parsing and a skills dictionary, entirely on our servers' : data.method}.</p></div>
          </div>
          <div>
            <h3>Technical skills ({x.skills.length})</h3>
            {x.skills.length === 0 ? <p className="muted small">No skills recognised. Add them on your profile.</p> : (
              <div className="tags">{x.skills.map((s) => <span className="tag" key={s.skill} title={s.evidence}>{s.skill}{s.mentions > 1 ? ` ×${s.mentions}` : ''}</span>)}</div>
            )}
            <p className="muted small" style={{ marginBottom: 0 }}>Hover over a skill to see the text it came from.</p>
          </div>
          {x.soft_skills.length > 0 && <div><h3>Soft skills</h3><div className="tags">{x.soft_skills.map((s) => <span className="tag" key={s.skill} title={s.evidence}>{s.skill}</span>)}</div></div>}
          <div>
            <h3>Experience</h3>
            {x.experience.length === 0 ? <p className="muted small">No dated roles found.</p> : (
              <ul className="list-plain">{x.experience.map((e, i) => <li key={i}><strong>{e.title}</strong>{e.company ? ` at ${e.company}` : ''} <span className="muted small">· {e.start} → {e.end} ({e.months} months)</span><div className="evidence">“{e.evidence}”</div></li>)}</ul>
            )}
          </div>
          <div>
            <h3>Education</h3>
            {x.education.length === 0 ? <p className="muted small">No education found.</p> : (
              <ul className="list-plain">{x.education.map((e, i) => <li key={i}><strong>{e.degree}</strong> <span className="muted small">· {e.level.replace('_', ' ')}{e.year ? ` · ${e.year}` : ''}</span><div className="evidence">“{e.evidence}”</div></li>)}</ul>
            )}
          </div>
          <div className="grid cols-2">
            <div><h3>Certifications</h3>{x.certifications.length === 0 ? <p className="muted small">None found.</p> : <ul className="list-plain">{x.certifications.map((c, i) => <li key={i}>{c.name || c}{evidence.certifications?.[c.name || c] && <div className="evidence">“{evidence.certifications[c.name || c]}”</div>}</li>)}</ul>}</div>
            <div><h3>Projects</h3>{x.projects.length === 0 ? <p className="muted small">None found.</p> : <ul className="list-plain">{x.projects.map((p, i) => <li key={i}>{p.name || p}</li>)}</ul>}</div>
          </div>
          <details><summary className="small">Show extracted text</summary><pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, maxHeight: 220, overflow: 'auto' }}>{data.text_preview}</pre></details>
          <div className="row">
            <button className="btn" onClick={confirm} disabled={action.busy || data.confirmed}>{data.confirmed ? '✓ Confirmed as accurate' : 'This looks right'}</button>
            <button className="btn secondary" onClick={onClose}>Close</button>
          </div>
        </div>
      )}
    </Modal>
  )
}

export default function Resume() {
  const { data, loading, error, reload } = useFetch('/candidate/resumes')
  const profile = useFetch('/candidate/profile')
  const [reviewId, setReviewId] = useState(null)
  const [drag, setDrag] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [uploading, setUploading] = useState(false)
  const input = useRef(null)
  const action = useAction()

  useEffect(() => {
    if (!data?.some((r) => PENDING.includes(r.status))) return undefined
    const timer = setInterval(reload, 2000)
    return () => clearInterval(timer)
  }, [data, reload])

  const upload = useCallback(async (file) => {
    setUploadError('')
    if (!file) return
    const name = file.name.toLowerCase()
    if (!name.endsWith('.pdf') && !name.endsWith('.docx')) return setUploadError('Please upload a PDF or DOCX file.')
    if (file.size > MAX_MB * 1024 * 1024) return setUploadError(`The file is larger than ${MAX_MB} MB.`)
    if (file.size === 0) return setUploadError('The file is empty.')
    const form = new FormData()
    form.append('file', file)
    setUploading(true)
    try {
      await api.post('/candidate/resumes', form)
      await reload()
    } catch (err) {
      setUploadError(errorMessage(err, 'Upload failed.'))
    } finally {
      setUploading(false)
      if (input.current) input.current.value = ''
    }
  }, [reload])

  const doAction = (fn) => async () => { const ok = await action.run(async () => { await fn(); return true }); if (ok) reload() }

  return (
    <div className="container page stack">
      <div className="page-head"><div><h1>Resume</h1><p>Upload your CV once. We extract your details and show them to you for review.</p></div></div>
      <div
        className={`dropzone ${drag ? 'drag' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files[0]) }}
      >
        <p><strong>Drag and drop your CV here</strong> or choose a file</p>
        <label className="btn" htmlFor="cv-input" style={{ cursor: 'pointer', display: 'inline-flex', width: 'auto' }}>{uploading ? 'Uploading…' : 'Choose PDF or DOCX'}</label>
        <input id="cv-input" ref={input} className="sr-only" type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(e) => upload(e.target.files[0])} disabled={uploading} />
        <p className="muted small" style={{ margin: '0.75rem 0 0' }}>Maximum {MAX_MB} MB. Your CV stays private and is only shared with employers you apply to or choose to share it with.</p>
      </div>
      <Alert>{uploadError || error || action.error}</Alert>

      {profile.data && (
        <section className="card stack-sm">
          <h3>Privacy</h3>
          <PrivacyToggle profile={profile.data} onSaved={profile.reload} />
        </section>
      )}

      {loading && <Spinner />}
      {data && data.length === 0 && <Empty title="No CV uploaded yet">Upload a CV to unlock match percentages and recommendations.</Empty>}
      <div className="stack">
        {data?.map((r) => (
          <article className="card" key={r.id}>
            <div className="row between">
              <div>
                <strong>{r.filename}</strong> {r.is_active && <Badge tone="brand">Active</Badge>} <StatusPill resume={r} />
                <div className="muted small">{(r.size_bytes / 1024).toFixed(0)} KB · uploaded {formatDate(r.uploaded_at, true)}</div>
              </div>
              <div className="row">
                {r.status === 'processed' && <button className="btn small" onClick={() => setReviewId(r.id)}>Review extracted data</button>}
                {r.status === 'processed' && !r.is_active && <button className="btn secondary small" onClick={doAction(() => api.post(`/candidate/resumes/${r.id}/activate`))}>Make active</button>}
                {r.status === 'failed' && <button className="btn secondary small" onClick={doAction(() => api.post(`/candidate/resumes/${r.id}/reprocess`))}>Try again</button>}
                <button className="btn secondary small" onClick={() => action.run(() => downloadFile(`/candidate/resumes/${r.id}/download`, r.filename))}>Download</button>
                <button className="btn danger small" onClick={() => window.confirm('Delete this resume?') && doAction(() => api.delete(`/candidate/resumes/${r.id}`))()}>Delete</button>
              </div>
            </div>
            {/* {r.status === 'failed' && <Alert>{r.error || 'We could not read this file. Make sure it is a text-based PDF or a DOCX, not a scan or password-protected.'}</Alert>} */}
            {r.status === 'processed' && !r.confirmed && <p className="small" style={{ margin: '0.5rem 0 0', color: 'var(--warn)' }}>Please review the extracted information to confirm it is accurate.</p>}
          </article>
        ))}
      </div>
      {reviewId && <Review id={reviewId} onClose={() => setReviewId(null)} onChanged={reload} />}
    </div>
  )
}

function PrivacyToggle({ profile, onSaved }) {
  const action = useAction()
  const save = (patch) => action.run(async () => { await api.put('/candidate/profile', patch); onSaved() })
  return (
    <div className="stack-sm">
      <label className="check"><input type="checkbox" checked={Boolean(profile.resume_visible_to_employers)} onChange={(e) => save({ resume_visible_to_employers: e.target.checked })} /><span>Let employers who find me in candidate search download my CV<br /><span className="muted small">Employers you apply to can always see your CV.</span></span></label>
      <label className="check"><input type="checkbox" checked={Boolean(profile.discoverable)} onChange={(e) => save({ discoverable: e.target.checked })} /><span>Make my profile discoverable to employers and recruiters<br /><span className="muted small">Your name, headline, skills and location become searchable. Contact details stay hidden until you apply.</span></span></label>
      <label className="check"><input type="checkbox" checked={Boolean(profile.ai_processing_consent)} onChange={(e) => save({ ai_processing_consent: e.target.checked })} /><span>Allow optional external AI processing of my CV text<br /><span className="muted small">Off by default. Pathwise works fully without it and never sends your CV to third parties without this consent.</span></span></label>
      <Alert>{action.error}</Alert>
    </div>
  )
}
