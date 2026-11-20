import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import api, { downloadFile } from '../../api'
import { useAction, useFetch } from '../../hooks'
import MatchPanel from '../../components/MatchPanel'
import { Alert, Empty, Field, MatchBadge, Modal, Spinner, StatusBadge } from '../../components/ui'
import { STATUS_LABELS, formatDate, timeAgo } from '../../utils'

const ACTIONS = [
  ['under_review', 'Mark under review'],
  ['shortlisted', 'Shortlist'],
  ['offer', 'Make offer'],
  ['rejected', 'Reject'],
]

const TRANSITIONS = {
  submitted: ['under_review', 'shortlisted', 'rejected'],
  viewed: ['under_review', 'shortlisted', 'rejected'],
  under_review: ['shortlisted', 'rejected'],
  shortlisted: ['under_review', 'offer', 'rejected'],
  interview_scheduled: ['shortlisted', 'offer', 'rejected'],
  offer: ['rejected'],
  rejected: [],
  withdrawn: [],
}
const CAN_INTERVIEW = ['under_review', 'shortlisted']

function InterviewForm({ applicationId, onDone }) {
  const [form, setForm] = useState({ date: '', time: '10:00', duration_minutes: 30, mode: 'video', location_or_link: '', notes: '' })
  const action = useAction()
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })
  const submit = async (event) => {
    event.preventDefault()
    const scheduled_at = new Date(`${form.date}T${form.time}`).toISOString()
    const ok = await action.run(async () => {
      await api.post(`/hiring/applications/${applicationId}/interviews`, {
        scheduled_at, duration_minutes: Number(form.duration_minutes), mode: form.mode,
        location_or_link: form.location_or_link || null, notes: form.notes || null,
      })
      return true
    })
    if (ok) onDone()
  }
  return (
    <form className="card flat stack" onSubmit={submit}>
      <h3 style={{ margin: 0 }}>Schedule interview</h3>
      <div className="form-grid">
        <Field label="Date" htmlFor="iv-d"><input id="iv-d" type="date" required min={new Date().toISOString().slice(0, 10)} value={form.date} onChange={set('date')} /></Field>
        <Field label="Time" htmlFor="iv-t"><input id="iv-t" type="time" required value={form.time} onChange={set('time')} /></Field>
        <Field label="Duration (minutes)" htmlFor="iv-m"><input id="iv-m" type="number" min="10" max="480" step="5" value={form.duration_minutes} onChange={set('duration_minutes')} /></Field>
        <Field label="Format" htmlFor="iv-f"><select id="iv-f" value={form.mode} onChange={set('mode')}><option value="video">Video call</option><option value="phone">Phone</option><option value="onsite">On-site</option></select></Field>
        <Field label="Link or address" htmlFor="iv-l" className="full"><input id="iv-l" value={form.location_or_link} onChange={set('location_or_link')} /></Field>
        <Field label="Notes for the candidate" htmlFor="iv-n" className="full"><textarea id="iv-n" rows={2} value={form.notes} onChange={set('notes')} /></Field>
      </div>
      <Alert>{action.error}</Alert>
      <div><button className="btn" disabled={action.busy}>Send invitation</button></div>
    </form>
  )
}

function Detail({ id, onChanged, onClose }) {
  const { data, loading, error, reload } = useFetch(`/hiring/applications/${id}`)
  const action = useAction()
  const [note, setNote] = useState('')
  const [message, setMessage] = useState('')
  const [scheduling, setScheduling] = useState(false)

  useEffect(() => { onChanged() }, [data?.status]) // eslint-disable-line react-hooks/exhaustive-deps

  const changeStatus = (status) => action.run(async () => {
    await api.post(`/hiring/applications/${id}/status`, { status, note: note || null })
    setNote('')
    reload()
  })
  const send = async (event) => {
    event.preventDefault()
    const ok = await action.run(async () => { await api.post(`/hiring/applications/${id}/messages`, { body: message }); return true })
    if (ok) { setMessage(''); reload() }
  }
  const resume = () => action.run(() => downloadFile(`/hiring/applications/${id}/resume`, 'resume'))

  return (
    <Modal title={data ? `${data.candidate.name} · ${data.job.title}` : 'Application'} onClose={onClose} wide>
      {loading && <Spinner />}
      <Alert>{error}</Alert>
      {data && (
        <div className="stack">
          <div className="row between">
            <div>
              <StatusBadge status={data.status} /> <span className="muted small">Applied {timeAgo(data.created_at)}</span>
              <div className="small">{data.candidate.email}{data.candidate.phone ? ` · ${data.candidate.phone}` : ''}{data.candidate.location ? ` · ${data.candidate.location}` : ''}</div>
            </div>
            <MatchBadge score={data.match_score} />
          </div>
          <div className="row">
            {(TRANSITIONS[data.status] || []).map((s) => {
              const label = ACTIONS.find(([k]) => k === s)?.[1]
              return label ? <button key={s} className={`btn small ${s === 'rejected' ? 'secondary' : ''}`} disabled={action.busy} onClick={() => changeStatus(s)}>{label}</button> : null
            })}
            {CAN_INTERVIEW.includes(data.status) && <button className="btn small" onClick={() => setScheduling(!scheduling)}>Schedule interview</button>}
            {data.has_resume && <button className="btn secondary small" onClick={resume}>Download CV</button>}
            <Link className="btn ghost small" to={`/employer/candidates?open=${data.candidate.id}&job_id=${data.job.id}`}>Full profile</Link>
          </div>
          <Field label="Note added to status change (optional)" htmlFor="sn"><input id="sn" maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          <Alert>{action.error}</Alert>
          {scheduling && <InterviewForm applicationId={id} onDone={() => { setScheduling(false); reload() }} />}
          {data.interviews.length > 0 && (
            <section><h3>Interviews</h3>{data.interviews.map((i) => <div key={i.id} className="small">{formatDate(i.scheduled_at, true)} · {i.duration_minutes} min · {i.mode} · {i.status}</div>)}</section>
          )}
          {data.cover_letter && <section><h3>Cover letter</h3><p style={{ whiteSpace: 'pre-wrap' }}>{data.cover_letter}</p></section>}
          {data.match && <MatchPanel match={data.match} audience="employer" />}
          <section className="grid cols-2">
            <div><h3>Experience</h3>{data.profile.experience.length === 0 && <p className="muted small">None listed</p>}{data.profile.experience.map((e) => <div key={e.id} className="small"><strong>{e.title}</strong>{e.company ? ` · ${e.company}` : ''}<br /><span className="muted">{e.start_date || ''}{e.end_date ? ` – ${e.end_date}` : ''}</span></div>)}</div>
            <div><h3>Education</h3>{data.profile.education.length === 0 && <p className="muted small">None listed</p>}{data.profile.education.map((e) => <div key={e.id} className="small"><strong>{e.degree}</strong>{e.institution ? ` · ${e.institution}` : ''}</div>)}</div>
          </section>
          <section>
            <h3>Status history</h3>
            <ul className="timeline">{data.history.map((h, i) => <li key={i}><strong>{STATUS_LABELS[h.to] || h.to}</strong> <span className="muted small">{formatDate(h.at, true)}{h.note ? ` · ${h.note}` : ''}</span></li>)}</ul>
          </section>
          <section className="stack-sm">
            <h3>Messages</h3>
            {data.messages.length === 0 && <p className="muted small">No messages yet.</p>}
            {data.messages.map((m) => <div key={m.id} className="card flat small" style={{ marginLeft: m.mine ? 'auto' : 0, maxWidth: '85%' }}><span className="muted">{m.mine ? 'You' : data.candidate.name} · {timeAgo(m.at)}</span><br />{m.body}</div>)}
            <form className="row" onSubmit={send}>
              <div style={{ flex: 1, minWidth: 200 }}><label className="sr-only" htmlFor="msg">Message</label><input id="msg" required maxLength={3000} placeholder="Write to the candidate" value={message} onChange={(e) => setMessage(e.target.value)} /></div>
              <button className="btn" disabled={action.busy}>Send</button>
            </form>
          </section>
        </div>
      )}
    </Modal>
  )
}

export default function EmployerApplications() {
  const [params, setParams] = useSearchParams()
  const jobId = params.get('job_id') || ''
  const status = params.get('status') || ''
  const sort = params.get('sort') || 'match'
  const open = params.get('open')
  const jobs = useFetch('/hiring/jobs')
  const { data, loading, error, reload } = useFetch('/hiring/applications', { job_id: jobId || undefined, status: status || undefined, sort })

  const update = (patch) => {
    const next = new URLSearchParams(params)
    Object.entries(patch).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)))
    setParams(next, { replace: true })
  }

  return (
    <div className="container page stack">
      <div className="page-head"><div><h1>Applications</h1><p>Review, shortlist and schedule interviews.</p></div></div>
      <div className="card row">
        <Field label="Job" htmlFor="fj"><select id="fj" value={jobId} onChange={(e) => update({ job_id: e.target.value, open: '' })}><option value="">All jobs</option>{jobs.data?.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}</select></Field>
        <Field label="Status" htmlFor="fs"><select id="fs" value={status} onChange={(e) => update({ status: e.target.value })}><option value="">All statuses</option>{Object.entries(STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
        <Field label="Sort by" htmlFor="fo"><select id="fo" value={sort} onChange={(e) => update({ sort: e.target.value })}><option value="match">Best match</option><option value="date">Most recent</option></select></Field>
      </div>
      <Alert>{error}</Alert>
      {loading && <Spinner />}
      {data && data.length === 0 && <Empty title="No applications found">Applications from candidates will show here with their compatibility score.</Empty>}
      {data?.length > 0 && (
        <div className="card table-wrap">
          <table className="table">
            <thead><tr><th>Candidate</th><th>Job</th><th>Match</th><th>Status</th><th>Applied</th><th><span className="sr-only">Open</span></th></tr></thead>
            <tbody>
              {data.map((a) => (
                <tr key={a.id}>
                  <td><strong>{a.candidate.name}</strong><div className="muted small">{a.candidate.headline || a.candidate.location || ''}</div></td>
                  <td>{a.job.title}</td>
                  <td><MatchBadge score={a.match_score} /></td>
                  <td><StatusBadge status={a.status} /></td>
                  <td>{timeAgo(a.created_at)}</td>
                  <td><button className="btn secondary small" onClick={() => update({ open: String(a.id) })}>Review</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {open && <Detail id={open} onChanged={reload} onClose={() => update({ open: '' })} />}
    </div>
  )
}
