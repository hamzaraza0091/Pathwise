import { useState } from 'react'
import api from '../../api'
import { useAction, useDebounced, useFetch } from '../../hooks'
import { Alert, Badge, Field, Pagination, Spinner } from '../../components/ui'

function Categories() {
  const { data, loading, error, reload } = useFetch('/admin/categories')
  const [name, setName] = useState('')
  const action = useAction()
  const add = async (event) => { event.preventDefault(); const ok = await action.run(async () => { await api.post('/admin/categories', { name }); return true }); if (ok) { setName(''); reload() } }
  const remove = (c) => action.run(async () => { await api.delete(`/admin/categories/${c.id}`); reload() })
  const rename = (c) => {
    const next = window.prompt('Rename category', c.name)
    if (next && next.trim() && next.trim() !== c.name) action.run(async () => { await api.put(`/admin/categories/${c.id}`, { name: next.trim() }); reload() })
  }
  return (
    <section className="card stack">
      <h2 style={{ margin: 0 }}>Job categories</h2>
      <Alert>{error || action.error}</Alert>
      {loading && <Spinner />}
      <ul className="list-plain">{data?.map((c) => (
        <li key={c.id} className="row between"><span>{c.name} <span className="muted small">{c.jobs} jobs</span></span><span className="row"><button className="btn ghost small" onClick={() => rename(c)}>Rename</button><button className="btn ghost small" disabled={c.jobs > 0 || action.busy} title={c.jobs > 0 ? 'In use by jobs' : ''} onClick={() => remove(c)}>Delete</button></span></li>
      ))}</ul>
      <form className="row" onSubmit={add}><div style={{ flex: 1 }}><label className="sr-only" htmlFor="nc">New category</label><input id="nc" required minLength={2} placeholder="New category" value={name} onChange={(e) => setName(e.target.value)} /></div><button className="btn" disabled={action.busy}>Add</button></form>
    </section>
  )
}

function Skills() {
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const dq = useDebounced(q)
  const { data, loading, error, reload } = useFetch('/admin/skills', { q: dq || undefined, page, page_size: 40 })
  const [form, setForm] = useState({ name: '', kind: 'technical', aliases: '' })
  const action = useAction()
  const add = async (event) => {
    event.preventDefault()
    const ok = await action.run(async () => { await api.post('/admin/skills', { name: form.name, kind: form.kind, aliases: form.aliases.split(',').map((s) => s.trim()).filter(Boolean) }); return true })
    if (ok) { setForm({ name: '', kind: 'technical', aliases: '' }); reload() }
  }
  const toggle = (s) => action.run(async () => { await api.put(`/admin/skills/${s.id}`, { name: s.name, kind: s.kind, aliases: s.aliases, is_active: !s.is_active }); reload() })
  const remove = (s) => action.run(async () => { await api.delete(`/admin/skills/${s.id}`); reload() })
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1
  return (
    <section className="card stack">
      <h2 style={{ margin: 0 }}>Skills taxonomy</h2>
      <p className="muted small" style={{ margin: 0 }}>The resume parser and matching engine recognise skills and aliases from this list.</p>
      <form className="row" onSubmit={add}>
        <Field label="Skill" htmlFor="sk-n"><input id="sk-n" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
        <Field label="Type" htmlFor="sk-k"><select id="sk-k" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}><option value="technical">Technical</option><option value="soft">Soft</option></select></Field>
        <Field label="Aliases (comma separated)" htmlFor="sk-a"><input id="sk-a" value={form.aliases} onChange={(e) => setForm({ ...form, aliases: e.target.value })} /></Field>
        <button className="btn" disabled={action.busy}>Add skill</button>
      </form>
      <label className="sr-only" htmlFor="sk-q">Filter skills</label>
      <input id="sk-q" type="search" placeholder="Filter skills" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} />
      <Alert>{error || action.error}</Alert>
      {loading && <Spinner />}
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Skill</th><th>Type</th><th>Aliases</th><th>Status</th><th /></tr></thead>
          <tbody>{data?.items.map((s) => (
            <tr key={s.id}><td>{s.name}</td><td>{s.kind}</td><td className="small">{s.aliases.join(', ') || '—'}</td><td>{s.is_active ? <Badge tone="success">Active</Badge> : <Badge tone="muted">Inactive</Badge>}</td>
              <td><div className="row"><button className="btn ghost small" disabled={action.busy} onClick={() => toggle(s)}>{s.is_active ? 'Deactivate' : 'Activate'}</button><button className="btn ghost small" disabled={action.busy} onClick={() => remove(s)}>Delete</button></div></td></tr>
          ))}</tbody>
        </table>
      </div>
      <Pagination page={page} pages={pages} onChange={setPage} />
    </section>
  )
}

export default function AdminTaxonomy() {
  return (
    <div className="container page stack">
      <div className="page-head"><div><h1>Skills and categories</h1><p>Maintain the vocabularies used for search, parsing and matching.</p></div></div>
      <Categories />
      <Skills />
    </div>
  )
}
