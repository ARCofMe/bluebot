"""Health endpoint regression tests."""

from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)


def test_health():
    """Ensure the health endpoint responds with HTTP 200."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"
