from fastapi.testclient import TestClient
from backend.main import app
from backend.database import connect
from io import BytesIO
from docx import Document
def login(client):
 response=client.post("/api/auth/login",json={"username":"owner","password":"test-password-long-enough"});assert response.status_code==200;return response.json()["csrf_token"]
def test_dashboard_health_and_authorization():
 with TestClient(app) as client:
  assert client.get("/").status_code==200;assert client.get("/api/health").json()["status"]=="ok";assert client.get("/api/jobs").status_code==401
  login(client);assert client.get("/api/jobs").status_code==200
def test_csrf_and_logout():
 with TestClient(app) as client:
  csrf=login(client);assert client.post("/api/runs").status_code==403;assert client.post("/api/auth/logout",headers={"X-CSRF-Token":csrf}).status_code==200;assert client.get("/api/jobs").status_code==401
def test_expired_session_is_rejected():
 with TestClient(app) as client:
  login(client)
  with connect() as db:db.execute("UPDATE sessions SET expires_at='2000-01-01T00:00:00+00:00'")
  assert client.get("/api/jobs").status_code==401
def test_sample_disabled_in_production(monkeypatch):
 monkeypatch.delenv("ALLOW_SAMPLE_SOURCE",raising=False)
 with TestClient(app) as client:
  csrf=login(client);assert client.post("/api/runs?sample=true",headers={"X-CSRF-Token":csrf}).status_code==200
  assert all(job["source"]!="sample" for job in client.get("/api/jobs").json())
def test_authenticated_cv_upload_and_parse():
 buffer=BytesIO();document=Document();document.add_paragraph("Verified factual profile");document.save(buffer)
 with TestClient(app) as client:
  csrf=login(client);response=client.post("/api/cv",headers={"X-CSRF-Token":csrf},files={"file":("resume.docx",buffer.getvalue(),"application/vnd.openxmlformats-officedocument.wordprocessingml.document")});assert response.status_code==200;assert "Verified factual profile" in response.json()["parsed_text"]
def test_document_download_requires_authentication(tmp_path):
 private=tmp_path/"private.docx";private.write_bytes(b"PK private")
 with connect() as db:document_id=db.execute("INSERT INTO documents(document_type,local_path,created_at) VALUES('CV',?,'2026-01-01')",(str(private),)).lastrowid
 with TestClient(app) as client:
  assert client.get(f"/api/documents/{document_id}/download").status_code==401
