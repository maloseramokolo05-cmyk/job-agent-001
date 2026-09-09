import base64
from fastapi.testclient import TestClient
from backend.config import app_base_url
from backend.main import app

def basic(user,password):
 token=base64.b64encode(f"{user}:{password}".encode()).decode()
 return {"Authorization":f"Basic {token}"}

def test_render_external_hostname_builds_public_url(monkeypatch):
 monkeypatch.delenv("APP_BASE_URL",raising=False)
 monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME","tumelo-job-agent.onrender.com")
 assert app_base_url()=="https://tumelo-job-agent.onrender.com"

def test_hosted_auth_guards_private_workspace(monkeypatch):
 monkeypatch.setenv("APP_AUTH_ENABLED","true")
 monkeypatch.setenv("APP_USERNAME","tumelo")
 monkeypatch.setenv("APP_PASSWORD","strong-test-password")
 with TestClient(app) as client:
  assert client.get("/api/health").status_code==200
  assert client.get("/").status_code==401
  assert client.get("/",headers=basic("tumelo","wrong")).status_code==401
  assert client.get("/",headers=basic("tumelo","strong-test-password")).status_code==200
