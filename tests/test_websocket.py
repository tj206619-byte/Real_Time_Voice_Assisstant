import pytest
import json
from fastapi.testclient import TestClient
from backend.main import app

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_health_endpoint(client):
    """Test health check REST endpoint."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["app"] == "VoicePilot"

def test_reminders_and_tasks_endpoints(client):
    """Test GET /api/reminders and /api/tasks endpoints."""
    res_rem = client.get("/api/reminders")
    assert res_rem.status_code == 200
    assert "reminders" in res_rem.json()

    res_tsk = client.get("/api/tasks")
    assert res_tsk.status_code == 200
    assert "tasks" in res_tsk.json()

def test_test_turn_endpoint(client):
    """Test POST /api/test/turn endpoint."""
    payload = {"message": "What is the weather in Bangalore?"}
    res = client.post("/api/test/turn", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "response_text" in data
    assert len(data["tools_called"]) > 0

def test_websocket_barge_in(client):
    """Test WebSocket session message exchange and interrupt handling."""
    with client.websocket_connect("/ws/voice") as websocket:
        # Start session
        websocket.send_text(json.dumps({"type": "session_start"}))
        
        # Read state response
        msg = json.loads(websocket.receive_text())
        assert msg["type"] in ["state", "data_update"]

        # Send an interrupt message
        websocket.send_text(json.dumps({"type": "interrupt"}))
