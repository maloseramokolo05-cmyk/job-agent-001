import os
import subprocess
import sys


def test_vercel_preview_entrypoint_starts_without_production_database():
    env = os.environ.copy()
    env["VERCEL"] = "1"
    env["VERCEL_ENV"] = "preview"
    env.pop("DATABASE_URL", None)
    env.pop("DATABASE_PATH", None)
    env.pop("APP_ENV", None)

    script = """
from fastapi.testclient import TestClient
from api.index import app

with TestClient(app) as client:
    response = client.get('/')
    assert response.status_code == 200, response.text
    assert 'Tumelo Job Agent' in response.text
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
