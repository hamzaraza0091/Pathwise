import { useEffect, useRef } from 'react'
import { MODE_LABELS, STATUS_LABELS, STATUS_TONE, TYPE_LABELS, matchTone } from '../utils'

export function Spinner({ label = 'Loading…' }) {
  return (
    <div className="loading" role="status">
      <div className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  )
}

export function Alert({ kind = 'error', children }) {
  if (!children) return null
  return (
    <div className={`alert ${kind}`} role={kind === 'error' ? 'alert' : 'status'}>
      {children}
    </div>
  )
}

export function Empty({ title, children, action }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  )
}

export function Badge({ tone = 'neutral', children }) {
  return <span className={`badge ${tone}`}>{children}</span>
}

export function StatusBadge({ status }) {
  return <Badge tone={STATUS_TONE[status] || 'neutral'}>{STATUS_LABELS[status] || status}</Badge>
}

export function ModeBadge({ mode }) {
  return mode ? <Badge tone="brand">{MODE_LABELS[mode] || mode}</Badge> : null
}

export function TypeLabel({ value }) {
  return TYPE_LABELS[value] || value || ''
}

export function MatchBadge({ score }) {
  if (score == null) return null
  return (
    <span className={`match ${matchTone(score)}`} title="Estimated profile-to-job compatibility, not a hiring probability" aria-label={`${score} percent match`}>
      <span>{score}%</span>
      <small>match</small>
    </span>
  )
}

export function Field({ label, hint, error, children, htmlFor, className = '' }) {
  return (
    <div className={`field ${className}`}>
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && <span className="hint">{hint}</span>}
      {error && <span className="hint" style={{ color: 'var(--danger)' }}>{error}</span>}
    </div>
  )
}

export function Pagination({ page, pages, onChange }) {
  if (!pages || pages <= 1) return null
  const numbers = []
  for (let n = Math.max(1, page - 2); n <= Math.min(pages, page + 2); n += 1) numbers.push(n)
  return (
    <nav className="pagination" aria-label="Pagination">
      <button className="btn secondary small" disabled={page <= 1} onClick={() => onChange(page - 1)}>Previous</button>
      {numbers.map((n) => (
        <button key={n} className={`btn small ${n === page ? '' : 'secondary'}`} aria-current={n === page ? 'page' : undefined} onClick={() => onChange(n)}>{n}</button>
      ))}
      <button className="btn secondary small" disabled={page >= pages} onClick={() => onChange(page + 1)}>Next</button>
    </nav>
  )
}

export function Modal({ title, onClose, children, wide }) {
  const ref = useRef(null)
  useEffect(() => {
    const previous = document.activeElement
    ref.current?.focus()
    const onKey = (event) => event.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      previous?.focus?.()
    }
  }, [onClose])
  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="btn ghost small" onClick={onClose} aria-label="Close dialog">✕</button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function Highlight({ html }) {
  if (!html) return null
  const safe = String(html)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/&lt;mark&gt;/g, '<mark>')
    .replace(/&lt;\/mark&gt;/g, '</mark>')
  return <span dangerouslySetInnerHTML={{ __html: safe }} />
}

export function ProgressBar({ value }) {
  return (
    <div className="progress" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
      <span style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  )
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map(([key, label]) => (
        <button key={key} role="tab" aria-selected={value === key} onClick={() => onChange(key)}>{label}</button>
      ))}
    </div>
  )
}
