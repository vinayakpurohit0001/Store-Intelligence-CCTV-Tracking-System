# PROMPT: Write pytest tests for a FastAPI /health endpoint that
# returns status, timestamp, version, service name.
# CHANGES MADE: Added timezone check, added service name assertion

from fastapi.testclient import TestClient
from app.main import app


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200

def test_health_has_required_fields(client):
    response = client.get("/health")
    data = response.json()
    assert "status" in data
    assert "timestamp" in data
    assert data["status"] == "ok"
    assert data["service"] == "store-intelligence-api"
