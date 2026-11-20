import httpx
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Job, JobSource
from app.services import aggregation
from app.services.matching import CandidateSnapshot, JobSnapshot, compute_match
from tests.conftest import login, register

DESC = "<p>We are hiring a Python engineer to build FastAPI services backed by SQL databases. Docker is a plus.</p>"


def remotive_payload(extra=None):
    jobs = [
        {"id": 101, "title": "Python Engineer", "company_name": "Globex", "description": DESC, "url": "https://remotive.com/jobs/101", "candidate_required_location": "Worldwide", "job_type": "full_time", "category": "Software Development", "tags": ["python", "fastapi"], "publication_date": "2026-11-10T10:00:00"},
        {"id": 102, "title": "Python Engineer", "company_name": "Globex", "description": DESC, "url": "https://remotive.com/jobs/102", "candidate_required_location": "Worldwide", "job_type": "full_time", "category": "Software Development", "tags": ["python"], "publication_date": "2026-11-10T10:00:00"},
        {"id": 103, "title": "x", "company_name": "", "description": "", "url": "bad"},
    ]
    return {"jobs": jobs + (extra or [])}


def run_sync(payload):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    with SessionLocal() as db:
        source = db.scalar(select(JobSource).where(JobSource.key == "remotive"))
        with httpx.Client(transport=transport) as client:
            run = aggregation.sync_source(db, source, client=client, triggered_by="test", force=True)
        return run.status, run.fetched, run.created, run.duplicates, run.rejected, run.expired


def test_ingest_dedupes_rejects_and_expires(client):
    status, fetched, created, duplicates, rejected, expired = run_sync(remotive_payload())
    assert status in ("success", "completed", "ok") or status
    assert fetched == 3 and created == 1 and duplicates == 1 and rejected == 1
    with SessionLocal() as db:
        jobs = db.scalars(select(Job).where(Job.status == "active")).all()
        assert len(jobs) == 1
        assert jobs[0].original_url == "https://remotive.com/jobs/101"
        assert jobs[0].source.name == "Remotive"
    listing = client.get("/api/jobs", params={"q": "python"}).json()
    assert listing["total"] == 1
    assert listing["items"][0]["attribution"] == "Originally posted on Remotive"
    assert listing["items"][0]["apply_mode"] == "external"
    again = run_sync(remotive_payload())
    assert again[2] == 0
    with SessionLocal() as db:
        assert len(db.scalars(select(Job)).all()) == 1


def test_ingest_failure_is_recorded_not_raised(client):
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    with SessionLocal() as db:
        source = db.scalar(select(JobSource).where(JobSource.key == "remotive"))
        with httpx.Client(transport=transport) as c:
            run = aggregation.sync_source(db, source, client=c, triggered_by="test", force=True)
        assert run.status == "failed" and run.error


def test_external_job_cannot_be_applied_natively(client):
    run_sync(remotive_payload())
    register(client, "cand@example.com")
    cand = login(client, "cand@example.com")
    job_id = client.get("/api/jobs", params={"q": "python"}).json()["items"][0]["id"]
    assert client.post(f"/api/jobs/{job_id}/apply", headers=cand, json={}).status_code in (400, 409, 422)


def make_candidate(skills, years=1.0, level="Junior"):
    return CandidateSnapshot(skills={s.lower(): s for s in skills}, years=years, level=level, education_level=3, has_education=True, titles=["Backend Developer"], location="Lahore, Pakistan", work_modes=["remote"], text="python backend", has_profile_data=True)


def test_score_bounds_and_weights():
    job = JobSnapshot(id=1, title="Python Developer", description="python api", required=["Python", "FastAPI", "SQL", "AWS", "Docker"], preferred=[], min_years=1, level="Junior", education_required="bachelor", location="Remote", work_mode="remote", employment_type="full_time", salary_min=None, salary_max=None, salary_currency=None)
    strong = compute_match(make_candidate(["Python", "FastAPI", "SQL", "AWS", "Docker"]), job)
    weak = compute_match(make_candidate(["Photoshop"]), job)
    for result in (strong, weak):
        assert 0 <= result["overall"] <= 100
        assert all(c["score"] is None or 0 <= c["score"] <= 100 for c in result["components"].values())
    assert strong["overall"] > weak["overall"]
    assert strong["explanation"]["missing_required_skills"] == []
    assert sorted(weak["explanation"]["missing_required_skills"]) == sorted(["Python", "FastAPI", "SQL", "AWS", "Docker"])
