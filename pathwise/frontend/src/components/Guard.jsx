import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { HOME_BY_ROLE, useAuth } from '../auth'
import { Spinner } from './ui'

export default function Guard({ roles }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="container page"><Spinner /></div>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  if (roles && !roles.includes(user.role)) return <Navigate to={HOME_BY_ROLE[user.role]} replace />
  return <Outlet />
}
