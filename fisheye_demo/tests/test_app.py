"""
tests/test_app.py — API Endpoint Tests

Dùng Flask test client + pytest-mock để mock services.
"""

import pytest
import json


@pytest.fixture
def app():
    from app import create_app
    from config import Config
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
    
    def test_health_has_status_ok(self, client):
        resp = client.get("/api/health")
        data = json.loads(resp.data)
        assert data["status"] == "ok"


class TestDetectEndpoint:
    def test_detect_without_file_returns_400(self, client):
        resp = client.post("/api/detect")
        assert resp.status_code == 400
    
    def test_detect_with_invalid_extension_returns_400(self, client, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("not an image")
        with open(test_file, "rb") as f:
            resp = client.post(
                "/api/detect",
                data={"file": (f, "test.txt")},
                content_type="multipart/form-data"
            )
        assert resp.status_code == 400


class TestJobEndpoints:
    def test_get_nonexistent_job_returns_404(self, client):
        resp = client.get("/api/jobs/nonexistent-id")
        assert resp.status_code == 404
    
    def test_list_jobs_returns_200(self, client):
        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "jobs" in data
