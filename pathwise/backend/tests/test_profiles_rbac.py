from tests.conftest import login, register


def test_candidate_profile_roundtrip_and_completion(client):
    register(client, "cand@example.com")
    headers = login(client, "cand@example.com")
    before = client.get("/api/candidate/profile", headers=headers).json()["completion"]
    response = client.put(
        "/api/candidate/profile",
        headers=headers,
        json={"headline": "Python developer", "summary": "Builds APIs", "location": "Islamabad", "years_experience": 1.5, "experience_level": "Junior"},
    )
    assert response.status_code == 200
    assert response.json()["completion"] > before
    assert response.json()["headline"] == "Python developer"


def test_invalid_experience_level_rejected(client):
    register(client, "cand@example.com")
    headers = login(client, "cand@example.com")
    assert client.put("/api/candidate/profile", headers=headers, json={"experience_level": "Wizard"}).status_code == 422


def test_candidate_preferences(client):
    register(client, "cand@example.com")
    headers = login(client, "cand@example.com")
    payload = {"desired_titles": ["Backend Developer"], "work_modes": ["remote"], "min_salary": 1000, "open_to_relocation": True}
    assert client.put("/api/candidate/preferences", headers=headers, json=payload).status_code == 200
    stored = client.get("/api/candidate/preferences", headers=headers).json()
    assert stored["work_modes"] == ["remote"]
    assert stored["open_to_relocation"] is True


def test_employer_company_created_on_register_and_updated(client):
    register(client, "emp@example.com", role="employer", company_name="Acme Labs")
    headers = login(client, "emp@example.com")
    company = client.get("/api/employer/company", headers=headers).json()
    assert company["name"] == "Acme Labs"
    assert company["slug"] == "acme-labs"
    updated = client.put("/api/employer/company", headers=headers, json={"name": "Acme Labs", "industry": "AI", "location": "Lahore"})
    assert updated.json()["industry"] == "AI"


def test_company_slug_unique(client):
    register(client, "e1@example.com", role="employer", company_name="Acme")
    register(client, "e2@example.com", role="employer", company_name="Acme")
    first = client.get("/api/employer/company", headers=login(client, "e1@example.com")).json()
    second = client.get("/api/employer/company", headers=login(client, "e2@example.com")).json()
    assert first["slug"] != second["slug"]


def test_employer_without_company_can_create_one(client):
    register(client, "emp@example.com", role="employer")
    headers = login(client, "emp@example.com")
    assert client.get("/api/employer/company", headers=headers).status_code == 404
    created = client.put("/api/employer/company", headers=headers, json={"name": "Fresh Co"})
    assert created.status_code == 200
    assert client.get("/api/employer/company", headers=headers).json()["name"] == "Fresh Co"


def test_recruiter_profile(client):
    register(client, "rec@example.com", role="recruiter")
    headers = login(client, "rec@example.com")
    response = client.put("/api/recruiter/profile", headers=headers, json={"specialization": "Engineering"})
    assert response.json()["specialization"] == "Engineering"


def test_role_isolation(client):
    register(client, "cand@example.com")
    register(client, "emp@example.com", role="employer", company_name="Acme")
    candidate = login(client, "cand@example.com")
    employer = login(client, "emp@example.com")
    assert client.get("/api/employer/company", headers=candidate).status_code == 403
    assert client.get("/api/candidate/profile", headers=employer).status_code == 403
    assert client.get("/api/recruiter/profile", headers=candidate).status_code == 403
    assert client.get("/api/admin/users", headers=candidate).status_code == 403
    assert client.get("/api/admin/users", headers=employer).status_code == 403


def test_admin_user_management(client):
    register(client, "cand@example.com")
    admin = login(client, "admin@example.com", "AdminPass123")
    users = client.get("/api/admin/users", headers=admin, params={"q": "cand"}).json()
    assert users["total"] == 1
    user_id = users["items"][0]["id"]
    assert client.patch(f"/api/admin/users/{user_id}", headers=admin, json={"is_active": False}).status_code == 200
    blocked = client.post("/api/auth/login", json={"email": "cand@example.com", "password": "Password123"})
    assert blocked.status_code == 403
    logs = client.get("/api/admin/audit-logs", headers=admin).json()
    assert any(entry["action"] == "admin.user_update" for entry in logs)


def test_deactivated_user_token_rejected(client):
    register(client, "cand@example.com")
    headers = login(client, "cand@example.com")
    admin = login(client, "admin@example.com", "AdminPass123")
    user_id = client.get("/api/admin/users", headers=admin, params={"q": "cand"}).json()["items"][0]["id"]
    client.patch(f"/api/admin/users/{user_id}", headers=admin, json={"is_active": False})
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_admin_cannot_modify_self(client):
    admin = login(client, "admin@example.com", "AdminPass123")
    admin_id = client.get("/api/auth/me", headers=admin).json()["id"]
    assert client.patch(f"/api/admin/users/{admin_id}", headers=admin, json={"is_active": False}).status_code == 400
