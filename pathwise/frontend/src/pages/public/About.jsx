import { Link } from 'react-router-dom'

const WEIGHTS = [['Skills compatibility', '45%'], ['Experience', '20%'], ['Education', '10%'], ['Location and work arrangement', '10%'], ['Semantic similarity of CV and job text', '10%'], ['Your preferences', '5%']]

export default function About() {
  return (
    <div className="container page stack" style={{ maxWidth: 860 }}>
      <div>
        <h1>About Pathwise</h1>
        <p className="muted">Pathwise brings jobs from authorized job feeds and direct employers into one place and compares each one with your CV.</p>
      </div>
      <section className="card">
        <h2>How matching works</h2>
        <p>The match percentage is a weighted blend of six scores, each between 0 and 100. When a dimension does not apply to a job (for example, no education requirement), its weight is redistributed so you are not penalised for missing information.</p>
        <div className="table-wrap">
          <table className="table"><tbody>{WEIGHTS.map(([k, v]) => <tr key={k}><td>{k}</td><td><strong>{v}</strong></td></tr>)}</tbody></table>
        </div>
        <p style={{ marginTop: '0.75rem' }}><strong>This percentage estimates profile-to-job compatibility. It is not the probability that you will be interviewed or hired.</strong> Gender, ethnicity, religion, age, photographs and other protected characteristics are never used.</p>
      </section>
      <section className="card">
        <h2>Where jobs come from</h2>
        <p>We only collect listings through official APIs and feeds, respecting each source's terms and update frequency. Every external job states where it was originally posted and links to the original application page. Pathwise never pretends to submit an external application for you.</p>
      </section>
      <section className="card">
        <h2>Your CV and privacy</h2>
        <p>Your CV is stored privately. Employers can only see it if you applied to one of their jobs or chose to share it. Your CV text is never sent to third-party AI services without your explicit consent.</p>
      </section>
      <div className="row"><Link className="btn" to="/register">Create an account</Link><Link className="btn secondary" to="/jobs">Browse jobs</Link></div>
    </div>
  )
}
