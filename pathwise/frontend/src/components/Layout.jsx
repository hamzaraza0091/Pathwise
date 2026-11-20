import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import api from '../api'
import { HOME_BY_ROLE, useAuth } from '../auth'

const NAV = {
  public: [['/jobs', 'Find jobs'], ['/companies', 'Companies'], ['/about', 'About']],
  candidate: [
    ['/candidate', 'Dashboard', true],
    ['/jobs', 'Find jobs'],
    ['/candidate/recommended', 'Recommended'],
    ['/candidate/saved', 'Saved'],
    ['/candidate/applications', 'Applications'],
    ['/candidate/resume', 'Resume'],
    ['/candidate/profile', 'Profile'],
  ],
  employer: [
    ['/employer', 'Dashboard', true],
    ['/employer/jobs', 'Jobs'],
    ['/employer/applications', 'Applications'],
    ['/employer/candidates', 'Candidates'],
    ['/employer/interviews', 'Interviews'],
    ['/employer/analytics', 'Analytics'],
    ['/employer/company', 'Company'],
  ],
  admin: [
    ['/admin', 'Dashboard', true],
    ['/admin/users', 'Users'],
    ['/admin/companies', 'Companies'],
    ['/admin/jobs', 'Jobs'],
    ['/admin/sources', 'Sources'],
    ['/admin/ingestion', 'Ingestion'],
    ['/admin/reports', 'Reports'],
    ['/admin/taxonomy', 'Skills & categories'],
    ['/admin/settings', 'Settings'],
  ],
}

function Mark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg width="18" height="18" viewBox="0 0 32 32"><path d="M9 24V9h8a4.5 4.5 0 010 9h-5" stroke="white" strokeWidth="3.4" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </span>
  )
}

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [open, setOpen] = useState(false)
  const [unread, setUnread] = useState(0)

  useEffect(() => setOpen(false), [location.pathname])

  useEffect(() => {
    if (!user) {
      setUnread(0)
      return undefined
    }
    let cancelled = false
    const load = () =>
      api.get('/notifications/unread-count').then(({ data }) => !cancelled && setUnread(data.unread ?? data.count ?? 0)).catch(() => {})
    load()
    const timer = setInterval(load, 60000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [user, location.pathname])

  const links = user ? NAV[user.role === 'recruiter' ? 'employer' : user.role] : NAV.public

  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      <header className="topbar">
        <div className="container">
          <Link to={user ? HOME_BY_ROLE[user.role] : '/'} className="brand"><Mark />Pathwise</Link>
          <button className="btn secondary small menu-toggle" aria-expanded={open} aria-controls="main-nav" onClick={() => setOpen(!open)}>Menu</button>
          <nav id="main-nav" className={`nav ${open ? 'open' : ''}`} aria-label="Main">
            {links.map(([to, label, end]) => (
              <NavLink key={to} to={to} end={end}>{label}</NavLink>
            ))}
            {user && (
              <NavLink to="/notifications">
                Notifications{unread > 0 && <span className="nav-count" aria-label={`${unread} unread`}>{unread}</span>}
              </NavLink>
            )}
            {user && <NavLink to="/account">Account</NavLink>}
            {!user && (
              <>
                <NavLink to="/login">Sign in</NavLink>
                <NavLink to="/register">Register</NavLink>
              </>
            )}
            {user && (
              <button className="btn secondary small" onClick={async () => { await logout(); navigate('/') }}>Sign out</button>
            )}
          </nav>
        </div>
      </header>
      <main id="main"><Outlet /></main>
      <footer className="footer">
        <div className="container row between">
          <span>© {new Date().getFullYear()} Pathwise. Match scores estimate profile-to-job compatibility, not hiring outcomes.</span>
          <span className="row"><Link to="/about">About</Link><Link to="/jobs">Jobs</Link><Link to="/companies">Companies</Link></span>
        </div>
      </footer>
    </>
  )
}
