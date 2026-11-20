import os
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["PATHWISE_DATABASE_URL"] = f"sqlite:///{Path(_tmp) / 'test.db'}"
os.environ["PATHWISE_STORAGE_DIR"] = _tmp
os.environ["PATHWISE_RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["PATHWISE_AUTH_RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["PATHWISE_WORKER_ENABLED"] = "false"
os.environ["PATHWISE_AUTO_CREATE_TABLES"] = "true"
os.environ["PATHWISE_ADMIN_EMAIL"] = "admin@example.com"
os.environ["PATHWISE_ADMIN_PASSWORD"] = "AdminPass123"

import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, engine
from app.main import app, seed


@pytest.fixture()
def client():
    with engine.begin() as c:
        c.exec_driver_sql("DROP TABLE IF EXISTS jobs_fts")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    seed()
    with TestClient(app) as c:
        yield c


def register(client, email, role="candidate", name="Test User", company_name=None):
    body = {"email": email, "password": "Password123", "full_name": name, "role": role}
    if company_name:
        body["company_name"] = company_name
    return client.post("/api/auth/register", json=body)


def login(client, email, password="Password123"):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
