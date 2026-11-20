import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => {
  const api = { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }
  return {
    default: api,
    tokenStore: { get: vi.fn(() => localStorage.getItem('pathwise_token')), set: (v) => localStorage.setItem('pathwise_token', v), clear: () => localStorage.removeItem('pathwise_token') },
    errorMessage: (e) => e?.response?.data?.detail || 'Something went wrong. Please try again.',
    downloadFile: vi.fn(),
  }
})

import api from '../api'
import App from '../App'
import { AuthProvider } from '../auth'

const candidate = { id: 1, email: 'c@example.com', full_name: 'Cara Candidate', role: 'candidate', email_verified: true, email_preferences: {} }
const dashboard = { stats: { recommended_total: 0, high_match_jobs: 0, applied: 0, saved: 0, under_review: 0, by_status: {} }, completion: 40, recommended: [], applications: [], skills: [], skill_suggestions: [], search_history: [], email_preferences: {}, resume: null, needs_profile: true }
const employer = { id: 2, email: 'e@example.com', full_name: 'Eli Employer', role: 'employer', email_verified: true, email_preferences: {} }

function mount(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider><App /></AuthProvider>
    </MemoryRouter>,
  )
}

function route(handlers) {
  api.get.mockImplementation((url, config) => {
    for (const [prefix, value] of Object.entries(handlers)) {
      if (url === prefix || url.startsWith(`${prefix}/`) || url === prefix) {
        return Promise.resolve({ data: typeof value === 'function' ? value(url, config) : value })
      }
    }
    return Promise.resolve({ data: {} })
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
})

describe('authentication and guards', () => {
  it('sends anonymous visitors from a protected route to the login page', async () => {
    route({})
    mount('/candidate')
    expect(await screen.findByRole('heading', { name: /welcome back/i })).toBeInTheDocument()
  })

  it('logs in and lands on the role dashboard', async () => {
    route({ '/auth/me': candidate, '/notifications/unread-count': { unread: 0 }, '/candidate/dashboard': dashboard })
    api.post.mockResolvedValue({ data: { access_token: 'tok', user: candidate } })
    mount('/login')
    await userEvent.type(await screen.findByLabelText(/email/i), 'c@example.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'Secret123')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/auth/login', { email: 'c@example.com', password: 'Secret123' }))
    await waitFor(() => expect(localStorage.getItem('pathwise_token')).toBe('tok'))
    await waitFor(() => expect(screen.queryByRole('heading', { name: /welcome back/i })).not.toBeInTheDocument())
  })

  it('shows the server message when credentials are wrong', async () => {
    route({})
    api.post.mockRejectedValue({ response: { status: 401, data: { detail: 'Incorrect email or password' } } })
    mount('/login')
    await userEvent.type(await screen.findByLabelText(/email/i), 'x@example.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'nope')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))
    expect(await screen.findByText(/incorrect email or password/i)).toBeInTheDocument()
  })

  it('redirects a candidate away from employer pages', async () => {
    localStorage.setItem('pathwise_token', 'tok')
    route({ '/auth/me': candidate, '/notifications/unread-count': { unread: 0 }, '/candidate/dashboard': dashboard })
    mount('/employer/jobs')
    await waitFor(() => expect(screen.queryByRole('heading', { name: /manage jobs/i })).not.toBeInTheDocument())
    expect(screen.queryByRole('link', { name: /^candidates$/i })).not.toBeInTheDocument()
  })
})

describe('employer flows', () => {
  beforeEach(() => localStorage.setItem('pathwise_token', 'tok'))

  it('publishes a job with parsed skills and numeric fields', async () => {
    route({ '/auth/me': employer, '/notifications/unread-count': { unread: 0 }, '/jobs/meta': { categories: [{ id: 1, name: 'Data & AI' }] } })
    api.post.mockResolvedValue({ data: { id: 9 } })
    mount('/employer/jobs/new')
    await userEvent.type(await screen.findByLabelText(/job title/i), 'Junior Python Developer')
    await userEvent.type(screen.getByLabelText(/^required skills/i), 'Python, FastAPI, , SQL, python')
    await userEvent.type(screen.getByLabelText(/^description/i), 'Build and maintain REST APIs with FastAPI and SQL databases.')
    await userEvent.type(screen.getByLabelText(/minimum years/i), '1')
    await userEvent.click(screen.getByRole('button', { name: /publish job/i }))
    await waitFor(() => expect(api.post).toHaveBeenCalled())
    const [url, body] = api.post.mock.calls[0]
    expect(url).toBe('/hiring/jobs')
    expect(body.required_skills).toEqual(['Python', 'FastAPI', 'SQL', 'python'])
    expect(body.min_years).toBe(1)
    expect(body.salary_min).toBeNull()
    expect(body.salary_currency).toBeNull()
  })

  it('lists applications with match scores and moves one to shortlisted', async () => {
    const application = { id: 5, status: 'submitted', match_score: 88, created_at: new Date().toISOString(), candidate: { id: 3, name: 'Cara Candidate', headline: 'Python dev', location: 'Lahore' }, job: { id: 7, title: 'Backend Developer' } }
    const detail = { ...application, candidate: { ...application.candidate, email: 'c@example.com' }, has_resume: false, interviews: [], history: [{ to: 'submitted', at: new Date().toISOString() }], messages: [], match: null, profile: { experience: [], education: [], skills: [] }, cover_letter: null }
    route({
      '/auth/me': employer, '/notifications/unread-count': { unread: 0 }, '/hiring/jobs': [{ id: 7, title: 'Backend Developer' }],
      '/hiring/applications/5': detail, '/hiring/applications': [application],
    })
    api.post.mockResolvedValue({ data: {} })
    mount('/employer/applications?open=5')
    expect(await screen.findByText('Backend Developer', { selector: 'td' })).toBeInTheDocument()
    expect(screen.getAllByLabelText('88 percent match')).toHaveLength(2)
    await userEvent.click(await screen.findByRole('button', { name: /^shortlist$/i }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/hiring/applications/5/status', { status: 'shortlisted', note: null }))
  })
})
