from pathlib import Path

from backend.config import ROOT, database_path


def test_vercel_preview_without_database_url_uses_tmp(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "preview")

    assert database_path() == Path("/tmp/tumelo-job-agent-preview.db")


def test_explicit_database_path_still_wins(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    monkeypatch.setenv("DATABASE_PATH", "/tmp/custom-job-agent.db")

    assert database_path() == Path("/tmp/custom-job-agent.db")


def test_non_vercel_default_is_repo_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)

    assert database_path() == ROOT / "data/job_agent.db"
