import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Guard from './components/Guard'
import { Spinner } from './components/ui'
import Home from './pages/public/Home'
import Jobs from './pages/public/Jobs'
import JobDetail from './pages/public/JobDetail'
import About from './pages/public/About'
import { Companies, CompanyDetail } from './pages/public/Companies'
import { ForgotPassword, Login, Register, ResetPassword, VerifyEmail } from './pages/public/Auth'
import { Account, NotFound, Notifications } from './pages/Shared'
import CandidateDashboard from './pages/candidate/Dashboard'
import Profile from './pages/candidate/Profile'
import Resume from './pages/candidate/Resume'
import Recommended from './pages/candidate/Recommended'
import Saved from './pages/candidate/Saved'
import Applications from './pages/candidate/Applications'
const EmployerDashboard = lazy(() => import('./pages/employer/Dashboard'))
const Company = lazy(() => import('./pages/employer/Company'))
const ManageJobs = lazy(() => import('./pages/employer/ManageJobs'))
const JobForm = lazy(() => import('./pages/employer/JobForm'))
const EmployerApplications = lazy(() => import('./pages/employer/Applications'))
const Candidates = lazy(() => import('./pages/employer/Candidates'))
const Interviews = lazy(() => import('./pages/employer/Interviews'))
const EmployerAnalytics = lazy(() => import('./pages/employer/Analytics'))
const AdminDashboard = lazy(() => import('./pages/admin/Dashboard'))
const AdminUsers = lazy(() => import('./pages/admin/Users').then((m) => ({ default: m.AdminUsers })))
const AdminCompanies = lazy(() => import('./pages/admin/Users').then((m) => ({ default: m.AdminCompanies })))
const AdminJobs = lazy(() => import('./pages/admin/Jobs'))
const AdminSources = lazy(() => import('./pages/admin/Sources'))
const AdminIngestion = lazy(() => import('./pages/admin/Ingestion'))
const AdminReports = lazy(() => import('./pages/admin/Reports'))
const AdminTaxonomy = lazy(() => import('./pages/admin/Taxonomy'))
const AdminSettings = lazy(() => import('./pages/admin/Settings'))

export default function App() {
  return (
    <Suspense fallback={<div className="container page"><Spinner /></div>}>
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Home />} />
        <Route path="/jobs" element={<Jobs />} />
        <Route path="/jobs/:id" element={<JobDetail />} />
        <Route path="/companies" element={<Companies />} />
        <Route path="/companies/:id" element={<CompanyDetail />} />
        <Route path="/about" element={<About />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/verify-email" element={<VerifyEmail />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />

        <Route element={<Guard />}>
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/account" element={<Account />} />
        </Route>

        <Route element={<Guard roles={['candidate']} />}>
          <Route path="/candidate" element={<CandidateDashboard />} />
          <Route path="/candidate/profile" element={<Profile />} />
          <Route path="/candidate/resume" element={<Resume />} />
          <Route path="/candidate/recommended" element={<Recommended />} />
          <Route path="/candidate/saved" element={<Saved />} />
          <Route path="/candidate/applications" element={<Applications />} />
        </Route>

        <Route element={<Guard roles={['employer', 'recruiter']} />}>
          <Route path="/employer" element={<EmployerDashboard />} />
          <Route path="/employer/jobs" element={<ManageJobs />} />
          <Route path="/employer/jobs/new" element={<JobForm />} />
          <Route path="/employer/jobs/:id/edit" element={<JobForm />} />
          <Route path="/employer/applications" element={<EmployerApplications />} />
          <Route path="/employer/candidates" element={<Candidates />} />
          <Route path="/employer/interviews" element={<Interviews />} />
          <Route path="/employer/analytics" element={<EmployerAnalytics />} />
        </Route>
        <Route element={<Guard roles={['employer']} />}>
          <Route path="/employer/company" element={<Company />} />
        </Route>

        <Route element={<Guard roles={['admin']} />}>
          <Route path="/admin" element={<AdminDashboard />} />
          <Route path="/admin/users" element={<AdminUsers />} />
          <Route path="/admin/companies" element={<AdminCompanies />} />
          <Route path="/admin/jobs" element={<AdminJobs />} />
          <Route path="/admin/sources" element={<AdminSources />} />
          <Route path="/admin/ingestion" element={<AdminIngestion />} />
          <Route path="/admin/reports" element={<AdminReports />} />
          <Route path="/admin/taxonomy" element={<AdminTaxonomy />} />
          <Route path="/admin/settings" element={<AdminSettings />} />
        </Route>

        <Route path="/dashboard" element={<Navigate to="/" replace />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
    </Suspense>
  )
}
