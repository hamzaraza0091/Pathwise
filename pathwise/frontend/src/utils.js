export const STATUS_LABELS = {
  submitted: 'Submitted',
  viewed: 'Viewed',
  under_review: 'Under review',
  shortlisted: 'Shortlisted',
  interview_scheduled: 'Interview scheduled',
  offer: 'Offer',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
}

export const STATUS_TONE = {
  submitted: 'neutral',
  viewed: 'info',
  under_review: 'info',
  shortlisted: 'success',
  interview_scheduled: 'accent',
  offer: 'success',
  rejected: 'danger',
  withdrawn: 'muted',
}

export const MODE_LABELS = { remote: 'Remote', onsite: 'On-site', hybrid: 'Hybrid' }
export const TYPE_LABELS = {
  full_time: 'Full-time',
  part_time: 'Part-time',
  contract: 'Contract',
  internship: 'Internship',
  freelance: 'Freelance',
  temporary: 'Temporary',
}
export const LEVELS = ['Entry Level', 'Junior', 'Mid Level', 'Senior', 'Lead', 'Executive']
export const EDU_LEVELS = [
  ['high_school', 'High school'],
  ['diploma', 'Diploma'],
  ['bachelor', "Bachelor's"],
  ['master', "Master's"],
  ['phd', 'PhD'],
]

export function formatDate(value, withTime = false) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return withTime
    ? date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
    : date.toLocaleDateString(undefined, { dateStyle: 'medium' })
}

export function timeAgo(value) {
  if (!value) return ''
  const seconds = Math.max(0, (Date.now() - new Date(value).getTime()) / 1000)
  if (seconds < 3600) return `${Math.max(1, Math.floor(seconds / 60))}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  if (seconds < 86400 * 30) return `${Math.floor(seconds / 86400)}d ago`
  return formatDate(value)
}

export function formatSalary(salary) {
  if (!salary) return null
  const { min, max, currency, period } = salary
  const cur = currency || ''
  const fmt = (n) => (n >= 1000 ? `${Math.round(n / 1000)}k` : `${Math.round(n)}`)
  const range = min && max ? `${fmt(min)}–${fmt(max)}` : fmt(min || max)
  return `${cur} ${range}${period ? ` / ${period}` : ''}`.trim()
}

export function matchTone(score) {
  if (score == null) return 'muted'
  if (score >= 80) return 'success'
  if (score >= 60) return 'info'
  if (score >= 40) return 'warn'
  return 'danger'
}

export function toParams(filters) {
  const out = {}
  Object.entries(filters).forEach(([key, value]) => {
    if (Array.isArray(value)) {
      if (value.length) out[key] = value.join(',')
    } else if (value !== '' && value !== null && value !== undefined && value !== false) {
      out[key] = value
    }
  })
  return out
}
