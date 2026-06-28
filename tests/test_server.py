"""FastAPI server tests."""

import pytest
from fastapi.testclient import TestClient
from lcm_cli.dashboard.server import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_index_returns_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "LCM Dashboard" in resp.text


def test_api_channels_empty(client):
    resp = client.get("/api/channels")
    assert resp.status_code == 200
    assert resp.json() == []


def test_api_schema_unknown_channel(client):
    resp = client.get("/api/channels/nonexistent/schema")
    assert resp.status_code == 404


def test_api_history_empty(client):
    resp = client.get("/api/history?channel=test&fields=speed")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"speed": []}
