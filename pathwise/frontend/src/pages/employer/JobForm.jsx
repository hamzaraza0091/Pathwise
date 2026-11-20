import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import api from '../../api'
import { useAction, useFetch } from '../../hooks'
import { Alert, Field, Spinner } from '../../components/ui'
import { LEVELS, EDU_LEVELS, MODE_LABELS, TYPE_LABELS } from '../../utils'

const EMPTY = {
  title: '', description: '', location: '', work_mode: '', employment_type: 'full_time', experience_level: '', min_years: '',
  education_required: '', salary_min: '', salary_max: '', salary_currency: 'USD', salary_period: 'year', category: '',
  required_skills: '', preferred_skills: '', application_url: '', expires_at: '',
}

const toForm = (job) => ({
  ...EMPTY,
  title: job.title || '', description: job.description || '', location: job.location || '', work_mode: job.work_mode || '',
  employment_type: job.employment_type || 'full_time', experience_level: job.experience_level || '', min_years: job.min_years ?? '',
  education_required: job.education_required || '', salary_min: job.salary?.min ?? '', salary_max: job.salary?.max ?? '',
  salary_currency: job.salary?.currency || 'USD', salary_period: job.salary?.period || 'year', category: job.category || '',
  required_skills: (job.skills?.required || []).join(', '), preferred_skills: (job.skills?.preferred || []).join(', '),
  application_url: job.apply_url || '', expires_at: job.expires_at ? job.expires_at.slice(0, 10) : '',
})

const splitList = (text) => [...new Set(text.split(',').map((s) => s.trim()).filter(Boolean))]
const num = (v) => (v === '' || v === null ? null : Number(v))

export default function JobForm() {
  const { id } = useParams()
  const navigate = useNavigate()
  const editing = Boolean(id)
  const existing = useFetch(editing ? `/hiring/jobs/${id}` : null, undefined, { enabled: editing })
  const meta = useFetch('/jobs/meta')
  const [form, setForm] = useState(EMPTY)
  const action = useAction()

  useEffect(() => { if (existing.data) setForm(toForm(existing.data)) }, [existing.data])
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  if (editing && existing.loading) return <div className="container page"><Spinner /></div>
  if (editing && existing.error) return <div className="container page"><Alert>{existing.error}</Alert></div>

  const submit = async (event) => {
    event.preventDefault()
    const body = {
      title: form.title.trim(), description: form.description.trim(), location: form.location.trim() || null,
      work_mode: form.work_mode || null, employment_type: form.employment_type, experience_level: form.experience_level || null,
      min_years: num(form.min_years), education_required: form.education_required || null,
      salary_min: num(form.salary_min), salary_max: num(form.salary_max),
      salary_currency: form.salary_min !== '' || form.salary_max !== '' ? form.salary_currency || null : null,
      salary_period: form.salary_min !== '' || form.salary_max !== '' ? form.salary_period : null,
      category: form.category || null, required_skills: splitList(form.required_skills), preferred_skills: splitList(form.preferred_skills),
      application_url: form.application_url.trim() || null, expires_at: form.expires_at ? new Date(`${form.expires_at}T23:59:59Z`).toISOString() : null,
    }
    const saved = await action.run(async () => (editing ? (await api.put(`/hiring/jobs/${id}`, body)).data : (await api.post('/hiring/jobs', body)).data))
    if (saved) navigate('/employer/jobs')
  }

  const categories = meta.data?.categories || []

  return (
    <div className="container page stack" style={{ maxWidth: 860 }}>
      <div className="page-head"><div><h1>{editing ? 'Edit job' : 'Post a job'}</h1><p>Candidates see a match score based on the skills you list, so be specific.</p></div></div>
      <form className="card stack" onSubmit={submit}>
        <div className="form-grid">
          <Field label="Job title" htmlFor="jt" className="full"><input id="jt" required minLength={3} maxLength={300} value={form.title} onChange={set('title')} /></Field>
          <Field label="Location" htmlFor="jl"><input id="jl" value={form.location} onChange={set('location')} placeholder="City, country, or Worldwide" /></Field>
          <Field label="Work arrangement" htmlFor="jm"><select id="jm" value={form.work_mode} onChange={set('work_mode')}><option value="">Not specified</option>{Object.entries(MODE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <Field label="Employment type" htmlFor="je"><select id="je" value={form.employment_type} onChange={set('employment_type')}>{Object.entries(TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <Field label="Experience level" htmlFor="jx"><select id="jx" value={form.experience_level} onChange={set('experience_level')}><option value="">Not specified</option>{LEVELS.map((l) => <option key={l}>{l}</option>)}</select></Field>
          <Field label="Minimum years of experience" htmlFor="jy"><input id="jy" type="number" min="0" max="40" step="0.5" value={form.min_years} onChange={set('min_years')} /></Field>
          <Field label="Education required" htmlFor="jd"><select id="jd" value={form.education_required} onChange={set('education_required')}><option value="">Not required</option>{EDU_LEVELS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <Field label="Category" htmlFor="jc"><select id="jc" value={form.category} onChange={set('category')}><option value="">Not set</option>{categories.map((c) => <option key={c.name || c}>{c.name || c}</option>)}</select></Field>
          <Field label="Salary range" htmlFor="js1" className="full">
            <div className="row">
              <input id="js1" aria-label="Minimum salary" type="number" min="0" placeholder="Min" style={{ width: 130 }} value={form.salary_min} onChange={set('salary_min')} />
              <input aria-label="Maximum salary" type="number" min="0" placeholder="Max" style={{ width: 130 }} value={form.salary_max} onChange={set('salary_max')} />
              <input aria-label="Currency" maxLength={8} style={{ width: 90 }} value={form.salary_currency} onChange={set('salary_currency')} />
              <select aria-label="Salary period" style={{ width: 120 }} value={form.salary_period} onChange={set('salary_period')}><option value="year">per year</option><option value="month">per month</option><option value="hour">per hour</option></select>
            </div>
          </Field>
          <Field label="Required skills" htmlFor="jr" hint="Comma separated, e.g. Python, FastAPI, SQL" className="full"><input id="jr" value={form.required_skills} onChange={set('required_skills')} /></Field>
          <Field label="Preferred skills" htmlFor="jp" hint="Nice to have" className="full"><input id="jp" value={form.preferred_skills} onChange={set('preferred_skills')} /></Field>
          <Field label="Description" htmlFor="jdsc" hint="At least 30 characters" className="full"><textarea id="jdsc" required minLength={30} rows={10} value={form.description} onChange={set('description')} /></Field>
          <Field label="Expires on" htmlFor="jex" hint="Leave empty for the default listing period"><input id="jex" type="date" value={form.expires_at} onChange={set('expires_at')} /></Field>
          <Field label="External application URL" htmlFor="ja" hint="Optional. Leave empty to receive applications inside Pathwise."><input id="ja" type="url" placeholder="https://" value={form.application_url} onChange={set('application_url')} /></Field>
        </div>
        <Alert>{action.error}</Alert>
        <div className="row">
          <button className="btn" disabled={action.busy}>{action.busy ? 'Saving…' : editing ? 'Save changes' : 'Publish job'}</button>
          <button type="button" className="btn secondary" onClick={() => navigate('/employer/jobs')}>Cancel</button>
        </div>
      </form>
    </div>
  )
}
