from fastapi.testclient import TestClient

from api.index import app


def test_vercel_entrypoint_has_no_private_sign_in_routes():
    paths = {getattr(route, "path", None) for route in app.router.routes}
    assert "/api/auth/login" not in paths
    assert "/api/auth/logout" not in paths
    assert "/api/auth/session" not in paths
    assert "/api/google/callback" in paths
    assert "/api/google/connect" in paths


def test_vercel_entrypoint_is_open_and_keeps_security_headers():
    with TestClient(app) as client:
        assert client.get("/api/jobs").status_code == 200
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
