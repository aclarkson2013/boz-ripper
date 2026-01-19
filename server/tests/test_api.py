"""Basic API tests."""

import pytest
from fastapi.testclient import TestClient

from boz_server.main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


def test_root(client):
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Boz Ripper Server"
    assert "version" in data


def test_health(client):
    """Test health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_list_agents_empty(client):
    """Test listing agents when none registered."""
    response = client.get("/api/agents")
    assert response.status_code == 200
    assert response.json() == []


def test_register_agent(client):
    """Test agent registration."""
    response = client.post(
        "/api/agents/register",
        json={
            "agent_id": "test-agent-1",
            "name": "Test Agent",
            "capabilities": {"can_rip": True, "can_transcode": False},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == "test-agent-1"
    assert data["name"] == "Test Agent"
    assert data["status"] == "online"
