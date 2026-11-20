import { useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../api'
import { useAction, useFetch } from '../../hooks'
import { Alert, Empty, Field, MatchBadge, Modal, Spinner, StatusBadge } from '../../components/ui'
import { STATUS_LABELS, formatDate } from '../../utils'

const ACTIVE = ['submitted', 'viewed', 'under_review', 'shortlisted', 'interview_scheduled']

function Detail({ id, onClose, onChanged }) {
  const { data, loading, error, reload } = useFetch(`/candidate/applications/${id}`)
  const [message, setMessage] = useState('')
  const action = useAction()

  const withdraw = async () => {
    if (!window.confirm('Withdraw this application? This cannot be undone.')) return
    const ok = await action.run(async () => { await api.post(`/candidate/applications/${id}/withdraw`); return true })
    if (ok) { await reload(); onChanged() }
  }
  const send = async (event) => {
    event.preventDefault()
    const ok = await action.run(async () => { await api.post(`/candidate/applications/${id}/messages`, { body: message }); return true })
    if (ok) { setMessage(''); reload() }
  }

  return (
    <Modal title={data ? data.job.title : 'Application'} onClose={onClose} wide>
      {loading && <Spinner />}
      <Alert>{error || action.error}</Alert>
      {data && (
        <div className="stack">
          <div className="row between">
            <div className="muted">{data.job.company_name}{data.job.location ? ` · ${data.job.location}` : ''}</div>
            <div className="row"><MatchBadge score={data.match_score} /><StatusBadge status={data.status} /></div>
          </div>
          <div className="grid cols-2">
            <div>
              <h3>Status history</h3>
              <ul className="timeline">{data.history.map((h, i) => <li key={i}><strong>{STATUS_LABELS[h.to] || h.to}</strong> <span className="muted small">{formatDate(h.at, true)}</span>{h.note && <div className="small">{h.note}</div>}</li>)}</ul>
            </div>
            <div>
              <h3>Interviews</h3>
              {data.interviews.length === 0 ? <p className="muted small">No interviews scheduled.</p> : (
                <ul className="list-plain">{data.interviews.map((i) => (
                  <li key={i.id} className="card flat"><strong>{formatDate(i.scheduled_at, true)}</strong> · {i.duration_minutes} min · {i.mode}<br />{i.location_or_link && <span className="small">{/^https?:/.test(i.location_or_link) ? <a href={i.location_or_link} target="_blank" rel="noopener noreferrer">{i.location_or_link}</a> : i.location_or_link}</span>}{i.notes && <div className="small muted">{i.notes}</div>}</li>
                ))}</ul>
              )}
            </div>
          </div>
          <div>
            <h3>Messages</h3>
            {data.messages?.length ? (
              <ul className="list-plain">{data.messages.map((m) => <li key={m.id} className="card flat"><div className="small muted">{m.mine ? 'You' : 'Employer'} · {formatDate(m.at, true)}</div>{m.body}</li>)}</ul>
            ) : <p className="muted small">No messages yet.</p>}
            {ACTIVE.includes(data.status) && (
              <form className="stack-sm" onSubmit={send} style={{ marginTop: '0.75rem' }}>
                <Field label="Message the employer" htmlFor="msg"><textarea id="msg" required maxLength={3000} value={message} onChange={(e) => setMessage(e.target.value)} style={{ minHeight: 70 }} /></Field>
                <div><button className="btn small" disabled={action.busy}>Send message</button></div>
              </form>
            )}
          </div>
          <div className="row">
            <Link className="btn secondary small" to={`/jobs/${data.job.id}`}>View job</Link>
            {ACTIVE.includes(data.status) && <button className="btn danger small" onClick={withdraw} disabled={action.busy}>Withdraw application</button>}
          </div>
        </div>
      )}
    </Modal>
  )
}

export default function Applications() {
  const [filter, setFilter] = useState('')
  const [openId, setOpenId] = useState(null)
  const { data, loading, error, reload } = useFetch('/candidate/applications', { status: filter || undefined })

  return (
    <div className="container page stack">
      <div className="page-head">
        <div><h1>My applications</h1><p>Track every application you submitted through Pathwise.</p></div>
        <div className="field" style={{ minWidth: 200 }}>
          <label htmlFor="af" className="sr-only">Filter by status</label>
          <select id="af" value={filter} onChange={(e) => setFilter(e.target.value)}><option value="">All statuses</option>{Object.entries(STATUS_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        </div>
      </div>
      <Alert>{error}</Alert>
      {loading && <Spinner />}
      {data && data.length === 0 && <Empty title="No applications" action={<Link className="btn" to="/jobs">Find jobs</Link>}>Jobs from other websites open on their original site; applications there are not tracked here.</Empty>}
      {data && data.length > 0 && (
        <div className="card table-wrap">
          <table className="table">
            <thead><tr><th>Job</th><th>Company</th><th>Match</th><th>Status</th><th>Applied</th><th /></tr></thead>
            <tbody>
              {data.map((a) => (
                <tr key={a.id}>
                  <td><Link to={`/jobs/${a.job.id}`}>{a.job.title}</Link></td>
                  <td>{a.job.company_name}</td>
                  <td>{a.match_score != null ? `${a.match_score}%` : '—'}</td>
                  <td><StatusBadge status={a.status} />{a.interviews.length > 0 && a.status === 'interview_scheduled' && <div className="small muted">{formatDate(a.interviews[0].scheduled_at, true)}</div>}</td>
                  <td>{formatDate(a.created_at)}</td>
                  <td><button className="btn secondary small" onClick={() => setOpenId(a.id)}>Details</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {openId && <Detail id={openId} onClose={() => setOpenId(null)} onChanged={reload} />}
    </div>
  )
}
