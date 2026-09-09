from fastapi.testclient import TestClient
from backend.main import app
def test_dashboard_and_health():
 with TestClient(app) as c:
  assert c.get("/").status_code==200
  assert c.get("/api/health").json()["status"]=="ok"
  assert c.get("/api/jobs").status_code==200

def test_sample_ingestion():
 with TestClient(app) as c:
  assert c.post("/api/runs?sample=true").status_code==200
  # Background tasks complete before TestClient returns.
  assert len(c.get("/api/jobs").json())==1
