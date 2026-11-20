import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import api from '../../api'
import { HOME_BY_ROLE, useAuth } from '../../auth'
import { useAction } from '../../hooks'
import { Alert, Field, Spinner } from '../../components/ui'

export function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const action = useAction()

  const submit = async (event) => {
    event.preventDefault()
    const user = await action.run(() => login(email, password))
    if (user) navigate(location.state?.from || HOME_BY_ROLE[user.role], { replace: true })
  }

  return (
    <div className="container">
      <div className="auth-wrap card stack">
        <div><h1>Welcome back</h1><p className="muted" style={{ margin: 0 }}>Sign in to your Pathwise account.</p></div>
        <form className="stack" onSubmit={submit}>
          <Field label="Email" htmlFor="email"><input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          <Field label="Password" htmlFor="password"><input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
          <Alert>{action.error}</Alert>
          <button className="btn block" disabled={action.busy}>{action.busy ? 'Signing in…' : 'Sign in'}</button>
        </form>
        <div className="row between small"><Link to="/forgot-password">Forgot password?</Link><span>New here? <Link to="/register">Create an account</Link></span></div>
      </div>
    </div>
  )
}

const ROLE_OPTIONS = [
  ['candidate', 'Job seeker', 'Find jobs and see CV matches'],
  ['employer', 'Employer', 'Post jobs and manage hiring'],
  ['recruiter', 'Recruiter', 'Join an employer to review candidates'],
]

export function Register() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const initial = ROLE_OPTIONS.some(([r]) => r === params.get('role')) ? params.get('role') : 'candidate'
  const [form, setForm] = useState({ role: initial, full_name: '', email: '', password: '', company_name: '' })
  const action = useAction()
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  const submit = async (event) => {
    event.preventDefault()
    const payload = { ...form }
    if (payload.role !== 'employer') delete payload.company_name
    const user = await action.run(() => register(payload))
    if (user) navigate(HOME_BY_ROLE[user.role], { replace: true })
  }

  return (
    <div className="container">
      <div className="auth-wrap card stack" style={{ maxWidth: 520 }}>
        <div><h1>Create your account</h1><p className="muted" style={{ margin: 0 }}>It takes less than a minute.</p></div>
        <form className="stack" onSubmit={submit}>
          <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
            <legend style={{ fontWeight: 600, marginBottom: 6 }}>I am a</legend>
            <div className="grid cols-3">
              {ROLE_OPTIONS.map(([value, label, hint]) => (
                <label key={value} className="card flat" style={{ cursor: 'pointer', borderColor: form.role === value ? 'var(--brand)' : undefined, background: form.role === value ? 'var(--brand-soft)' : undefined, margin: 0 }}>
                  <input className="sr-only" type="radio" name="role" value={value} checked={form.role === value} onChange={set('role')} />
                  <strong>{label}</strong><br /><span className="small muted" style={{ fontWeight: 400 }}>{hint}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <Field label="Full name" htmlFor="name"><input id="name" required minLength={2} autoComplete="name" value={form.full_name} onChange={set('full_name')} /></Field>
          {form.role === 'employer' && <Field label="Company name" htmlFor="company"><input id="company" required minLength={2} value={form.company_name} onChange={set('company_name')} /></Field>}
          <Field label="Email" htmlFor="remail"><input id="remail" type="email" required autoComplete="email" value={form.email} onChange={set('email')} /></Field>
          <Field label="Password" htmlFor="rpass" hint="At least 8 characters with letters and numbers"><input id="rpass" type="password" required minLength={8} autoComplete="new-password" value={form.password} onChange={set('password')} /></Field>
          <Alert>{action.error}</Alert>
          <button className="btn block" disabled={action.busy}>{action.busy ? 'Creating account…' : 'Create account'}</button>
        </form>
        <p className="small muted" style={{ margin: 0 }}>Already registered? <Link to="/login">Sign in</Link></p>
      </div>
    </div>
  )
}

export function VerifyEmail() {
  const [params] = useSearchParams()
  const { refresh } = useAuth()
  const [state, setState] = useState({ status: 'working', message: '' })

  useEffect(() => {
    const token = params.get('token')
    if (!token) {
      setState({ status: 'error', message: 'This verification link is missing its token.' })
      return
    }
    api.post('/auth/verify-email', { token })
      .then(() => { setState({ status: 'ok', message: '' }); refresh() })
      .catch((err) => setState({ status: 'error', message: err.response?.data?.detail || 'This link is invalid or has expired.' }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="container"><div className="auth-wrap card stack">
      <h1>Email verification</h1>
      {state.status === 'working' && <Spinner label="Verifying…" />}
      {state.status === 'ok' && <Alert kind="success">Your email address is verified. Thank you!</Alert>}
      {state.status === 'error' && <Alert>{state.message}</Alert>}
      <Link to="/login">Continue</Link>
    </div></div>
  )
}

export function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const action = useAction()
  const submit = async (event) => {
    event.preventDefault()
    const ok = await action.run(async () => { await api.post('/auth/forgot-password', { email }); return true })
    if (ok) setSent(true)
  }
  return (
    <div className="container"><div className="auth-wrap card stack">
      <h1>Reset your password</h1>
      {sent ? <Alert kind="success">If an account exists for {email}, a reset link is on its way.</Alert> : (
        <form className="stack" onSubmit={submit}>
          <Field label="Email" htmlFor="fe"><input id="fe" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          <Alert>{action.error}</Alert>
          <button className="btn block" disabled={action.busy}>Send reset link</button>
        </form>
      )}
      <Link to="/login">Back to sign in</Link>
    </div></div>
  )
}

export function ResetPassword() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [password, setPassword] = useState('')
  const [done, setDone] = useState(false)
  const action = useAction()
  const submit = async (event) => {
    event.preventDefault()
    const ok = await action.run(async () => { await api.post('/auth/reset-password', { token: params.get('token') || '', password }); return true })
    if (ok) { setDone(true); setTimeout(() => navigate('/login'), 1500) }
  }
  return (
    <div className="container"><div className="auth-wrap card stack">
      <h1>Choose a new password</h1>
      {done ? <Alert kind="success">Password updated. Redirecting to sign in…</Alert> : (
        <form className="stack" onSubmit={submit}>
          <Field label="New password" htmlFor="np" hint="At least 8 characters with letters and numbers"><input id="np" type="password" minLength={8} required autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
          <Alert>{action.error}</Alert>
          <button className="btn block" disabled={action.busy}>Update password</button>
        </form>
      )}
    </div></div>
  )
}
