import io

from docx import Document

from tests.conftest import login, register

JOB = {
    "title": "Junior Python Developer",
    "description": "We need a Python developer to build FastAPI services with SQL databases. Docker and AWS knowledge is a plus. You will work with our machine learning team.",
    "location": "Remote",
    "work_mode": "remote",
    "employment_type": "full_time",
    "experience_level": "Junior",
    "category": "Software Development",
    "required_skills": ["Python", "FastAPI", "SQL", "Docker"],
    "preferred_skills": ["AWS"],
}


def cv_docx():
    doc = Document()
    doc.add_heading("Muhammad Hamza Raza", 0)
    doc.add_paragraph("Python developer. Email: hamza@example.com")
    doc.add_heading("Skills", 1)
    doc.add_paragraph("Python, FastAPI, SQL, Machine Learning, LangChain, Communication")
    doc.add_heading("Experience", 1)
    doc.add_paragraph("Backend Developer Intern at Acme, Jan 2024 - Dec 2024. Built FastAPI services with SQL.")
    doc.add_heading("Education", 1)
    doc.add_paragraph("Bachelor of Science in Computer Science, FAST University, 2024")
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def setup_world(client):
    register(client, "emp@example.com", role="employer", company_name="Acme Labs")
    emp = login(client, "emp@example.com")
    created = client.post("/api/hiring/jobs", headers=emp, json=JOB)
    assert created.status_code == 201, created.text
    register(client, "cand@example.com")
    cand = login(client, "cand@example.com")
    return emp, cand, created.json()["id"]


def upload_cv(client, cand):
    response = client.post("/api/candidate/resumes", headers=cand, files={"file": ("cv.docx", cv_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert response.status_code == 202, response.text
    return response.json()["id"]


def test_search_finds_native_job_and_pagination(client):
    emp, cand, job_id = setup_world(client)
    result = client.get("/api/jobs", params={"q": "python", "page": 1, "page_size": 5}).json()
    assert result["total"] == 1
    assert result["items"][0]["id"] == job_id
    assert result["items"][0]["attribution"] is None
    assert client.get("/api/jobs", params={"q": "nonexistentterm"}).json()["total"] == 0
    assert client.get("/api/jobs/suggestions", params={"q": "pyt"}).status_code == 200


def test_invalid_resume_rejected(client):
    emp, cand, job_id = setup_world(client)
    bad = client.post("/api/candidate/resumes", headers=cand, files={"file": ("cv.exe", b"MZ....", "application/octet-stream")})
    assert bad.status_code in (400, 415, 422)
    fake = client.post("/api/candidate/resumes", headers=cand, files={"file": ("cv.pdf", b"not a pdf at all", "application/pdf")})
    assert fake.status_code in (400, 415, 422) or client.get(f"/api/candidate/resumes/{fake.json()['id']}", headers=cand).json()["status"] == "failed"


def test_resume_extraction_match_and_apply_flow(client):
    emp, cand, job_id = setup_world(client)
    resume_id = upload_cv(client, cand)
    resume = client.get(f"/api/candidate/resumes/{resume_id}", headers=cand).json()
    assert resume["status"] == "processed", resume
    skills = {s["skill"].lower() for s in resume["extracted"]["skills"]}
    assert {"python", "fastapi", "sql"} <= skills

    assert client.post(f"/api/candidate/resumes/{resume_id}/confirm", headers=cand, json={}).status_code in (200, 422)

    match = client.get(f"/api/candidate/matches/{job_id}", headers=cand)
    assert match.status_code == 200, match.text
    body = match.json()["match"]
    assert 0 <= body["score"] <= 100
    assert any(m.lower() == "docker" for m in body["missing_required_skills"])
    assert any(m.lower() == "python" for m in body["matched_skills"])
    assert body["suggestions"] and body["disclaimer"]
    assert set(body["components"]) == {"skills", "experience", "education", "location", "semantic", "preferences"}
    assert all(0 <= c["score"] <= 100 for c in body["components"].values() if c["score"] is not None)

    recs = client.get("/api/candidate/recommendations", headers=cand).json()
    items = recs["items"] if isinstance(recs, dict) else recs
    assert any(i["id"] == job_id for i in items)
    assert all(i["match"] is not None for i in items)

    assert client.post(f"/api/jobs/{job_id}/save", headers=cand).status_code == 201
    assert len(client.get("/api/candidate/saved", headers=cand).json()) == 1

    applied = client.post(f"/api/jobs/{job_id}/apply", headers=cand, json={"cover_letter": "Hello"})
    assert applied.status_code == 201, applied.text
    assert client.post(f"/api/jobs/{job_id}/apply", headers=cand, json={}).status_code == 409
    app_id = applied.json()["id"]

    employer_apps = client.get("/api/hiring/applications", headers=emp).json()
    rows = employer_apps["items"] if isinstance(employer_apps, dict) else employer_apps
    assert len(rows) == 1 and rows[0]["match_score"] is not None

    assert client.post(f"/api/hiring/applications/{app_id}/status", headers=emp, json={"status": "shortlisted"}).status_code == 200
    interview = client.post(f"/api/hiring/applications/{app_id}/interviews", headers=emp, json={"scheduled_at": "2030-01-01T10:00:00Z", "mode": "video"})
    assert interview.status_code == 201, interview.text
    detail = client.get(f"/api/candidate/applications/{app_id}", headers=cand).json()
    assert detail["status"] == "interview_scheduled"
    assert [h["to"] for h in detail["history"]][-1] == "interview_scheduled"

    notes = client.get("/api/notifications", headers=cand).json()
    assert notes["total"] >= 1


def test_candidate_cannot_see_other_application_or_employer_cv(client):
    emp, cand, job_id = setup_world(client)
    upload_cv(client, cand)
    app_id = client.post(f"/api/jobs/{job_id}/apply", headers=cand, json={}).json()["id"]
    register(client, "other@example.com")
    other = login(client, "other@example.com")
    assert client.get(f"/api/candidate/applications/{app_id}", headers=other).status_code == 404
    register(client, "emp2@example.com", role="employer", company_name="Rival Inc")
    rival = login(client, "emp2@example.com")
    assert client.get(f"/api/hiring/applications/{app_id}", headers=rival).status_code == 404
    assert client.get(f"/api/hiring/applications/{app_id}/resume", headers=rival).status_code == 404
    assert client.get(f"/api/hiring/applications/{app_id}/resume", headers=emp).status_code == 200


def test_candidate_cannot_use_employer_routes(client):
    emp, cand, job_id = setup_world(client)
    assert client.post("/api/hiring/jobs", headers=cand, json=JOB).status_code == 403
    assert client.get("/api/admin/users", headers=cand).status_code == 403
    assert client.get("/api/hiring/jobs").status_code == 401


def test_admin_moderation(client):
    emp, cand, job_id = setup_world(client)
    admin = login(client, "admin@example.com", "AdminPass123")
    assert client.post(f"/api/jobs/{job_id}/report", headers=cand, json={"reason": "scam"}).status_code == 201
    reports = client.get("/api/admin/reports", headers=admin).json()
    assert reports["total"] == 1
    assert client.post(f"/api/admin/reports/{reports['items'][0]['id']}/resolve", headers=admin, json={"action": "remove_job"}).status_code == 200
    assert client.get("/api/jobs", params={"q": "python"}).json()["total"] == 0
    stats = client.get("/api/admin/analytics", headers=admin).json()
    assert stats["total_users"] >= 3
    sources = client.get("/api/admin/sources", headers=admin).json()
    assert any(s["key"] == "remotive" for s in sources)
    assert client.get("/api/admin/categories", headers=admin).status_code == 200
    bad = client.put("/api/admin/settings/matching_weights", headers=admin, json={"value": {"weights": {"skills": 1}}})
    assert bad.status_code == 400
    good = {"skills": 0.5, "experience": 0.2, "education": 0.1, "location": 0.1, "semantic": 0.05, "preferences": 0.05}
    assert client.put("/api/admin/settings/matching_weights", headers=admin, json={"value": {"weights": good}}).status_code == 200


def test_employer_analytics_and_close_job(client):
    emp, cand, job_id = setup_world(client)
    assert client.get("/api/hiring/analytics", headers=emp).json()["active_jobs"] == 1
    assert client.post(f"/api/hiring/jobs/{job_id}/close", headers=emp).status_code == 200
    assert client.get("/api/jobs", params={"q": "python"}).json()["total"] == 0
    assert client.post(f"/api/jobs/{job_id}/apply", headers=login(client, "cand@example.com") if False else {}, json={}).status_code == 401
