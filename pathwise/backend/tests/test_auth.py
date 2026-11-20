from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import EmailOutbox, User
from tests.conftest import login, register


def test_register_login_me(client):
    assert register(client, "a@example.com").status_code == 201
    headers = login(client, "a@example.com")
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["role"] == "candidate"
    assert "password_hash" not in me.json()


def test_duplicate_email_rejected(client):
    register(client, "a@example.com")
    assert register(client, "A@example.com").status_code == 409


def test_weak_password_rejected(client):
    response = client.post("/api/auth/register", json={"email": "b@example.com", "password": "short", "full_name": "Bee", "role": "candidate"})
    assert response.status_code == 422


def test_admin_cannot_self_register(client):
    response = client.post("/api/auth/register", json={"email": "c@example.com", "password": "Password123", "full_name": "Cee", "role": "admin"})
    assert response.status_code == 422


def test_wrong_password(client):
    register(client, "a@example.com")
    response = client.post("/api/auth/login", json={"email": "a@example.com", "password": "Wrong12345"})
    assert response.status_code == 401


def test_logout_revokes_session(client):
    register(client, "a@example.com")
    headers = login(client, "a@example.com")
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_unauthenticated_blocked(client):
    assert client.get("/api/auth/me").status_code == 401


def test_email_verification_flow(client):
    register(client, "a@example.com")
    with SessionLocal() as db:
        body = db.scalar(select(EmailOutbox.body).where(EmailOutbox.to_email == "a@example.com"))
    token = body.split("token=")[1].strip()
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 204
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 400
    with SessionLocal() as db:
        assert db.scalar(select(User.email_verified).where(User.email == "a@example.com")) is True


def test_password_reset_flow(client):
    register(client, "a@example.com")
    old_headers = login(client, "a@example.com")
    client.post("/api/auth/forgot-password", json={"email": "a@example.com"})
    with SessionLocal() as db:
        bodies = db.scalars(select(EmailOutbox.body).where(EmailOutbox.subject.like("Reset%"))).all()
    token = bodies[0].split("token=")[1].split("\n")[0].strip()
    assert client.post("/api/auth/reset-password", json={"token": token, "password": "NewPassword9"}).status_code == 204
    assert client.get("/api/auth/me", headers=old_headers).status_code == 401
    response = client.post("/api/auth/login", json={"email": "a@example.com", "password": "NewPassword9"})
    assert response.status_code == 200


def test_forgot_password_does_not_reveal_accounts(client):
    assert client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"}).status_code == 204


def test_email_preferences_update(client):
    register(client, "a@example.com")
    headers = login(client, "a@example.com")
    response = client.patch("/api/auth/me", headers=headers, json={"email_preferences": {"new_recommendations": False, "high_match_alerts": True, "application_updates": True, "interview_invitations": True}})
    assert response.json()["email_preferences"]["new_recommendations"] is False
