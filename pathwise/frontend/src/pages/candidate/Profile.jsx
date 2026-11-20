import { useEffect, useState } from 'react'
import api from '../../api'
import { useAction, useFetch } from '../../hooks'
import { Alert, Badge, Empty, Field, Modal, ProgressBar, Spinner } from '../../components/ui'
import { EDU_LEVELS, LEVELS, MODE_LABELS, TYPE_LABELS } from '../../utils'

const SECTIONS = {
  education: {
    title: 'Education',
    empty: 'Add your degrees and qualifications.',
    blank: { degree: '', level: 'bachelor', institution: '', field_of_study: '', end_year: '' },
    fields: [
      ['degree', 'Degree or qualification', 'text', true],
      ['level', 'Level', 'select', false, EDU_LEVELS],
      ['institution', 'Institution', 'text'],
      ['field_of_study', 'Field of study', 'text'],
      ['end_year', 'Graduation year', 'number'],
    ],
    line: (i) => [i.degree, i.institution, i.end_year].filter(Boolean).join(' · '),
  },
  experience: {
    title: 'Work experience',
    empty: 'Add jobs, internships or freelance work.',
    blank: { title: '', company: '', start_date: '', end_date: '', months: '', description: '' },
    fields: [
      ['title', 'Job title', 'text', true],
      ['company', 'Company', 'text'],
      ['start_date', 'Start (YYYY-MM)', 'text'],
      ['end_date', 'End (YYYY-MM or present)', 'text'],
      ['months', 'Duration in months', 'number'],
      ['description', 'Description', 'textarea'],
    ],
    line: (i) => [i.title, i.company, i.start_date && `${i.start_date} → ${i.end_date || '?'}`].filter(Boolean).join(' · '),
  },
  certifications: {
    title: 'Certifications',
    empty: 'Add certifications you hold.',
    blank: { name: '', description: '' },
    fields: [['name', 'Certification', 'text', true], ['description', 'Details', 'textarea']],
    line: (i) => i.name,
  },
  projects: {
    title: 'Projects',
    empty: 'Add projects that show your skills.',
    blank: { name: '', description: '' },
    fields: [['name', 'Project name', 'text', true], ['description', 'Description', 'textarea']],
    line: (i) => i.name,
  },
}

function clean(values) {
  const out = {}
  Object.entries(values).forEach(([k, v]) => {
    if (v === '' || v === null || v === undefined) return
    out[k] = ['end_year', 'months'].includes(k) ? Number(v) : v
  })
  return out
}

function ItemSection({ kind, items, onChanged }) {
  const cfg = SECTIONS[kind]
  const [editing, setEditing] = useState(null)
  const [values, setValues] = useState(cfg.blank)
  const action = useAction()

  const openNew = () => { setValues(cfg.blank); setEditing('new') }
  const openEdit = (item) => { setValues({ ...cfg.blank, ...Object.fromEntries(Object.entries(item).filter(([k]) => k in cfg.blank).map(([k, v]) => [k, v ?? ''])) }); setEditing(item) }
  const save = async (event) => {
    event.preventDefault()
    const ok = await action.run(async () => {
      if (editing === 'new') await api.post(`/candidate/${kind}`, clean(values))
      else await api.put(`/candidate/${kind}/${editing.id}`, clean(values))
      return true
    })
    if (ok) { setEditing(null); onChanged() }
  }
  const remove = async (item) => {
    if (!window.confirm('Remove this entry?')) return
    const ok = await action.run(async () => { await api.delete(`/candidate/${kind}/${item.id}`); return true })
    if (ok) onChanged()
  }

  return (
    <section className="card">
      <div className="row between"><h2 style={{ margin: 0 }}>{cfg.title}</h2><button className="btn secondary small" onClick={openNew}>+ Add</button></div>
      <Alert>{!editing && action.error}</Alert>
      {items.length === 0 ? <p className="muted">{cfg.empty}</p> : (
        <ul className="list-plain" style={{ marginTop: '0.75rem' }}>
          {items.map((item) => (
            <li key={item.id} className="row between">
              <span>{cfg.line(item)} {item.source === 'resume' && <Badge tone="info">from CV</Badge>}{item.description && <span className="muted small" style={{ display: 'block' }}>{item.description.slice(0, 160)}</span>}</span>
              <span className="row"><button className="btn ghost small" onClick={() => openEdit(item)}>Edit</button><button className="btn ghost small" onClick={() => remove(item)}>Remove</button></span>
            </li>
          ))}
        </ul>
      )}
      {editing && (
        <Modal title={`${editing === 'new' ? 'Add' : 'Edit'} ${cfg.title.toLowerCase()}`} onClose={() => setEditing(null)}>
          <form className="stack" onSubmit={save}>
            {cfg.fields.map(([name, label, type, required, options]) => (
              <Field key={name} label={label} htmlFor={`${kind}-${name}`}>
                {type === 'select' ? <select id={`${kind}-${name}`} value={values[name]} onChange={(e) => setValues({ ...values, [name]: e.target.value })}>{options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
                  : type === 'textarea' ? <textarea id={`${kind}-${name}`} value={values[name]} onChange={(e) => setValues({ ...values, [name]: e.target.value })} style={{ minHeight: 80 }} />
                  : <input id={`${kind}-${name}`} type={type} required={required} value={values[name]} onChange={(e) => setValues({ ...values, [name]: e.target.value })} />}
              </Field>
            ))}
            <Alert>{action.error}</Alert>
            <div className="row"><button className="btn" disabled={action.busy}>Save</button><button type="button" className="btn secondary" onClick={() => setEditing(null)}>Cancel</button></div>
          </form>
        </Modal>
      )}
    </section>
  )
}

function Skills({ skills, onChanged }) {
  const [name, setName] = useState('')
  const [kind, setKind] = useState('technical')
  const action = useAction()
  const add = async (event) => {
    event.preventDefault()
    const ok = await action.run(async () => { await api.post('/candidate/skills', { skill: name.trim(), kind }); return true })
    if (ok) { setName(''); onChanged() }
  }
  const remove = async (id) => { const ok = await action.run(async () => { await api.delete(`/candidate/skills/${id}`); return true }); if (ok) onChanged() }
  const groups = [['technical', 'Technical skills'], ['soft', 'Soft skills']]
  return (
    <section className="card stack">
      <h2 style={{ margin: 0 }}>Skills</h2>
      <p className="muted small" style={{ margin: 0 }}>Skills drive 45% of every match score. Only list skills you genuinely have.</p>
      {groups.map(([k, label]) => (
        <div key={k}>
          <h3>{label}</h3>
          <div className="tags">
            {skills.filter((s) => s.kind === k).map((s) => (
              <span className="tag" key={s.id} title={s.evidence || ''}>{s.skill}<button aria-label={`Remove ${s.skill}`} onClick={() => remove(s.id)}>×</button></span>
            ))}
            {skills.filter((s) => s.kind === k).length === 0 && <span className="muted small">None yet</span>}
          </div>
        </div>
      ))}
      <form className="row" onSubmit={add}>
        <div style={{ flex: 1, minWidth: 160 }}><label className="sr-only" htmlFor="new-skill">Skill name</label><input id="new-skill" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Add a skill, e.g. FastAPI" /></div>
        <div><label className="sr-only" htmlFor="new-kind">Type</label><select id="new-kind" value={kind} onChange={(e) => setKind(e.target.value)}><option value="technical">Technical</option><option value="soft">Soft</option></select></div>
        <button className="btn" disabled={action.busy}>Add skill</button>
      </form>
      <Alert>{action.error}</Alert>
    </section>
  )
}

function Preferences() {
  const { data, loading, reload } = useFetch('/candidate/preferences')
  const [form, setForm] = useState(null)
  const [saved, setSaved] = useState(false)
  const action = useAction()
  useEffect(() => {
    if (data) setForm({ ...data, desired_titles: (data.desired_titles || []).join(', '), preferred_locations: (data.preferred_locations || []).join(', '), min_salary: data.min_salary ?? '' })
  }, [data])
  if (loading || !form) return <Spinner />
  const list = (v) => v.split(',').map((s) => s.trim()).filter(Boolean)
  const toggle = (key, value) => setForm({ ...form, [key]: form[key].includes(value) ? form[key].filter((x) => x !== value) : [...form[key], value] })
  const save = async (event) => {
    event.preventDefault()
    setSaved(false)
    const ok = await action.run(async () => {
      await api.put('/candidate/preferences', { ...form, desired_titles: list(form.desired_titles), preferred_locations: list(form.preferred_locations), min_salary: form.min_salary === '' ? null : Number(form.min_salary), salary_currency: form.salary_currency || null })
      return true
    })
    if (ok) { setSaved(true); reload() }
  }
  return (
    <form className="card stack" onSubmit={save}>
      <h2 style={{ margin: 0 }}>Job preferences</h2>
      <div className="form-grid">
        <Field label="Desired job titles" htmlFor="pt" hint="Comma separated"><input id="pt" value={form.desired_titles} onChange={(e) => setForm({ ...form, desired_titles: e.target.value })} /></Field>
        <Field label="Preferred locations" htmlFor="pl" hint="Comma separated"><input id="pl" value={form.preferred_locations} onChange={(e) => setForm({ ...form, preferred_locations: e.target.value })} /></Field>
        <Field label="Minimum yearly salary" htmlFor="ps"><input id="ps" type="number" min="0" value={form.min_salary} onChange={(e) => setForm({ ...form, min_salary: e.target.value })} /></Field>
        <Field label="Currency" htmlFor="pc"><input id="pc" maxLength={8} value={form.salary_currency || ''} onChange={(e) => setForm({ ...form, salary_currency: e.target.value.toUpperCase() })} placeholder="USD" /></Field>
      </div>
      <div><span className="small" style={{ fontWeight: 600 }}>Work arrangement</span><div className="chips" style={{ marginTop: 6 }}>{Object.entries(MODE_LABELS).map(([v, l]) => <button type="button" key={v} className="chip" aria-pressed={form.work_modes.includes(v)} onClick={() => toggle('work_modes', v)}>{l}</button>)}</div></div>
      <div><span className="small" style={{ fontWeight: 600 }}>Employment type</span><div className="chips" style={{ marginTop: 6 }}>{Object.entries(TYPE_LABELS).map(([v, l]) => <button type="button" key={v} className="chip" aria-pressed={form.employment_types.includes(v)} onClick={() => toggle('employment_types', v)}>{l}</button>)}</div></div>
      <label className="check"><input type="checkbox" checked={form.open_to_relocation} onChange={(e) => setForm({ ...form, open_to_relocation: e.target.checked })} />Open to relocation</label>
      <Alert>{action.error}</Alert>
      <Alert kind="success">{saved && 'Preferences saved. Your recommendations will refresh.'}</Alert>
      <div><button className="btn" disabled={action.busy}>Save preferences</button></div>
    </form>
  )
}

export default function Profile() {
  const profile = useFetch('/candidate/profile')
  const data = useFetch('/candidate/profile-data')
  const [form, setForm] = useState(null)
  const [saved, setSaved] = useState(false)
  const action = useAction()

  useEffect(() => {
    if (profile.data) setForm(Object.fromEntries(['headline', 'summary', 'phone', 'location', 'years_experience', 'experience_level', 'linkedin_url', 'portfolio_url'].map((k) => [k, profile.data[k] ?? ''])))
  }, [profile.data])

  const reloadAll = () => { data.reload(); profile.reload() }

  const save = async (event) => {
    event.preventDefault()
    setSaved(false)
    const body = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v === '' ? null : k === 'years_experience' ? Number(v) : v]))
    const ok = await action.run(async () => { await api.put('/candidate/profile', body); return true })
    if (ok) { setSaved(true); profile.reload() }
  }

  if (profile.loading || !form) return <div className="container page"><Spinner /></div>
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  return (
    <div className="container page stack">
      <div className="page-head"><div><h1>Your profile</h1><p>The more complete your profile, the more accurate your matches.</p></div><div style={{ minWidth: 220 }}><div className="small" style={{ marginBottom: 4 }}>{profile.data.completion}% complete</div><ProgressBar value={profile.data.completion} /></div></div>
      <form className="card stack" onSubmit={save}>
        <h2 style={{ margin: 0 }}>Basics</h2>
        <div className="form-grid">
          <Field label="Professional headline" htmlFor="h" className="full"><input id="h" maxLength={255} value={form.headline} onChange={set('headline')} placeholder="e.g. Python developer focused on APIs and ML" /></Field>
          <Field label="Location" htmlFor="loc"><input id="loc" value={form.location} onChange={set('location')} placeholder="City, Country" /></Field>
          <Field label="Phone" htmlFor="ph"><input id="ph" value={form.phone} onChange={set('phone')} /></Field>
          <Field label="Years of experience" htmlFor="ye"><input id="ye" type="number" min="0" max="60" step="0.5" value={form.years_experience} onChange={set('years_experience')} /></Field>
          <Field label="Experience level" htmlFor="el"><select id="el" value={form.experience_level} onChange={set('experience_level')}><option value="">Not set</option>{LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}</select></Field>
          <Field label="LinkedIn URL" htmlFor="li"><input id="li" type="url" value={form.linkedin_url} onChange={set('linkedin_url')} /></Field>
          <Field label="Portfolio URL" htmlFor="po"><input id="po" type="url" value={form.portfolio_url} onChange={set('portfolio_url')} /></Field>
          <Field label="Summary" htmlFor="su" className="full"><textarea id="su" maxLength={5000} value={form.summary} onChange={set('summary')} /></Field>
        </div>
        <Alert>{action.error}</Alert>
        <Alert kind="success">{saved && 'Profile saved.'}</Alert>
        <div><button className="btn" disabled={action.busy}>Save profile</button></div>
      </form>
      {data.loading && <Spinner />}
      {data.data && (
        <>
          <Skills skills={data.data.skills} onChanged={reloadAll} />
          {['experience', 'education', 'certifications', 'projects'].map((k) => <ItemSection key={k} kind={k} items={data.data[k]} onChanged={reloadAll} />)}
        </>
      )}
      <Preferences />
    </div>
  )
}
