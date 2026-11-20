import api from '../../api'
import { useAction, useFetch } from '../../hooks'
import JobCard from '../../components/JobCard'
import { Alert, Empty, Spinner } from '../../components/ui'
import { Link } from 'react-router-dom'

export default function Saved() {
  const { data, loading, error, setData } = useFetch('/candidate/saved')
  const action = useAction()
  const unsave = (job) =>
    action.run(async () => {
      await api.delete(`/jobs/${job.id}/save`)
      setData((prev) => prev.filter((j) => j.id !== job.id))
    })
  return (
    <div className="container page stack">
      <div className="page-head"><div><h1>Saved jobs</h1><p>Jobs you bookmarked to come back to.</p></div></div>
      <Alert>{error || action.error}</Alert>
      {loading && <Spinner />}
      {data && data.length === 0 && <Empty title="No saved jobs yet" action={<Link className="btn" to="/jobs">Find jobs</Link>}>Tap Save on any job to keep it here.</Empty>}
      <div className="job-list">{data?.map((job) => <JobCard key={job.id} job={job} onSave={unsave} saving={action.busy} />)}</div>
    </div>
  )
}
