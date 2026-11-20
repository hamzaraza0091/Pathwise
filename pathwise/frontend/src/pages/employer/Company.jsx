import { useEffect, useState } from 'react'
import api from '../../api'
import { useAction, useFetch } from '../../hooks'
import { Alert, Badge, Empty, Field, Spinner } from '../../components/ui'

export default function Company() {
  const { data, loading, reload } = useFetch('/employer/company')
  const team = useFetch('/hiring/recruiters')
  const [form, setForm] = useState(null)
  const [saved, setSaved] = useState(false)
  const [recruiter, setRecruiter] = useState('')
  const action = useAction()
  const teamAction = useAction()

  useEffect(() => { if (data) setForm(Object.fromEntries(['name', 'website', 'industry', 'size', 'location', 'description', 'logo_url'].map((k) => [k, data[k] ?? '']))) }, [data])
  if (loading || !form) return <div className="container page"><Spinner /></div>
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  const save = async (event) => {
    event.preventDefault()
    setSaved(false)
    const body = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v === '' && k !== 'name' ? null : v]))
    const ok = await action.run(async () => { await api.put('/employer/company', body); return true })
    if (ok) { setSaved(true); reload() }
  }
  const attach = async (event) => {
    event.preventDefault()
    const ok = await teamAction.run(async () => { await api.post('/hiring/recruiters', { email: recruiter }); return true })
    if (ok) { setRecruiter(''); team.reload() }
  }
  const detach = async (id) => { const ok = await teamAction.run(async () => { await api.delete(`/hiring/recruiters/${id}`); return true }); if (ok) team.reload() }

  return (
    <div className="container page stack" style={{ maxWidth: 860 }}>
      <div className="page-head"><div><h1>Company profile</h1><p>{data.is_verified ? <Badge tone="success">Verified</Badge> : 'This is shown on your job postings.'}</p></div></div>
      <form className="card stack" onSubmit={save}>
        <div className="form-grid">
          <Field label="Company name" htmlFor="cn"><input id="cn" required minLength={2} value={form.name} onChange={set('name')} /></Field>
          <Field label="Website" htmlFor="cw"><input id="cw" type="url" value={form.website} onChange={set('website')} placeholder="https://" /></Field>
          <Field label="Industry" htmlFor="ci"><input id="ci" value={form.industry} onChange={set('industry')} /></Field>
          <Field label="Company size" htmlFor="cs"><select id="cs" value={form.size} onChange={set('size')}><option value="">Not set</option>{['1-10', '11-50', '51-200', '201-500', '501-1000', '1000+'].map((s) => <option key={s}>{s}</option>)}</select></Field>
          <Field label="Location" htmlFor="cl"><input id="cl" value={form.location} onChange={set('location')} /></Field>
          <Field label="Logo URL" htmlFor="cg"><input id="cg" type="url" value={form.logo_url} onChange={set('logo_url')} /></Field>
          <Field label="About the company" htmlFor="cd" className="full"><textarea id="cd" value={form.description} onChange={set('description')} maxLength={5000} /></Field>
        </div>
        <Alert>{action.error}</Alert>
        <Alert kind="success">{saved && 'Company profile saved.'}</Alert>
        <div><button className="btn" disabled={action.busy}>Save company</button></div>
      </form>
      <section className="card stack">
        <h2 style={{ margin: 0 }}>Recruiters</h2>
        <p className="muted small" style={{ margin: 0 }}>Recruiters register with the Recruiter role; add them by email to give them access to your jobs and applications.</p>
        {team.data?.length === 0 && <Empty title="No recruiters yet" />}
        <ul className="list-plain">{team.data?.map((r) => <li key={r.user_id} className="row between"><span>{r.name} <span className="muted small">{r.email}</span></span><button className="btn ghost small" onClick={() => detach(r.user_id)}>Remove</button></li>)}</ul>
        <form className="row" onSubmit={attach}>
          <div style={{ flex: 1, minWidth: 200 }}><label className="sr-only" htmlFor="re">Recruiter email</label><input id="re" type="email" required placeholder="recruiter@example.com" value={recruiter} onChange={(e) => setRecruiter(e.target.value)} /></div>
          <button className="btn" disabled={teamAction.busy}>Add recruiter</button>
        </form>
        <Alert>{teamAction.error}</Alert>
      </section>
    </div>
  )
}
