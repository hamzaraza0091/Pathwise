import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useFetch } from '../../hooks'
import { Alert, Spinner } from '../../components/ui'
import { STATUS_LABELS } from '../../utils'

const COLORS = ['#2557d6', '#12805c', '#a15c00', '#6a3fc4', '#1f6fb2', '#b3261e', '#5b6785', '#16203a']

export default function EmployerAnalytics() {
  const { data, loading, error } = useFetch('/hiring/analytics')
  if (loading) return <div className="container page"><Spinner /></div>
  if (error) return <div className="container page"><Alert>{error}</Alert></div>
  const pipeline = Object.entries(data.applications_by_status).map(([key, value]) => ({ name: STATUS_LABELS[key] || key, value }))
  const daily = data.daily_applications

  return (
    <div className="container page stack">
      <div className="page-head"><div><h1>Hiring analytics</h1><p>Activity across your jobs over the last 30 days.</p></div></div>
      <div className="grid cols-4">
        <div className="card stat"><span className="value">{data.active_jobs}</span><span className="label">Active jobs</span></div>
        <div className="card stat"><span className="value">{data.total_applications}</span><span className="label">Applications</span></div>
        <div className="card stat"><span className="value">{data.interviews}</span><span className="label">Interviews</span></div>
        <div className="card stat"><span className="value">{data.offer_rate}%</span><span className="label">Offer rate</span></div>
      </div>
      <div className="grid cols-2">
        <section className="card">
          <h2>Applications per day</h2>
          <div style={{ height: 260 }} role="img" aria-label="Line chart of daily applications">
            <ResponsiveContainer><LineChart data={daily}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="date" tickFormatter={(d) => d.slice(5)} minTickGap={24} /><YAxis allowDecimals={false} /><Tooltip /><Line type="monotone" dataKey="applications" stroke="#2557d6" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer>
          </div>
        </section>
        <section className="card">
          <h2>Pipeline</h2>
          {pipeline.length === 0 ? <p className="muted">No applications yet.</p> : (
            <div style={{ height: 260 }} role="img" aria-label="Pie chart of applications by status">
              <ResponsiveContainer><PieChart><Pie data={pipeline} dataKey="value" nameKey="name" outerRadius={90} label>{pipeline.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Pie><Tooltip /></PieChart></ResponsiveContainer>
            </div>
          )}
        </section>
      </div>
      <section className="card">
        <h2>Applications per job</h2>
        {data.per_job.length === 0 ? <p className="muted">No jobs posted yet.</p> : (
          <div style={{ height: Math.max(200, data.per_job.length * 44) }} role="img" aria-label="Bar chart of applications per job">
            <ResponsiveContainer><BarChart data={data.per_job} layout="vertical" margin={{ left: 40 }}><CartesianGrid strokeDasharray="3 3" /><XAxis type="number" allowDecimals={false} /><YAxis type="category" dataKey="title" width={180} /><Tooltip /><Bar dataKey="applications" fill="#2557d6" radius={[0, 4, 4, 0]} /></BarChart></ResponsiveContainer>
          </div>
        )}
      </section>
    </div>
  )
}
