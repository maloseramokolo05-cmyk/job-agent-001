from pathlib import Path
import shutil
import subprocess

import pytest

from applications.thresholds import effective_auto_prepare_threshold, effective_email_threshold
from job_sources.careers24 import _section


ROOT = Path(__file__).resolve().parents[1]


def test_email_threshold_has_safe_floor():
    assert effective_email_threshold({"email_minimum_score": 72}) == 80
    assert effective_email_threshold({"email_minimum_score": 90}) == 90


def test_auto_prepare_threshold_has_safe_floor():
    assert effective_auto_prepare_threshold({"auto_prepare_score": 70}) == 80
    assert effective_auto_prepare_threshold({"auto_prepare_score": 85}) == 85


def test_careers24_section_removes_recommendation_noise():
    raw = """
    Menu
    Vacancy Details
    Employer: Example Co
    Job Description:
    Support digital marketing campaigns and social media.
    Candidate Requirements
    BBA or related qualification.
    Similar Jobs
    Senior Engineer
    More Jobs at Example Co
    Accountant
    About Careers24.com
    Footer
    """
    cleaned = _section(raw)
    assert "Support digital marketing campaigns" in cleaned
    assert "BBA or related qualification" in cleaned
    assert "Senior Engineer" not in cleaned
    assert "Accountant" not in cleaned
    assert "About Careers24.com" not in cleaned


def test_careers24_section_starts_at_vacancy_details():
    cleaned = _section("Navigation noise\nVacancy Details\nReal vacancy text\nAbout Careers24.com\nFooter")
    assert cleaned.startswith("Vacancy Details")
    assert "Navigation noise" not in cleaned
    assert "Footer" not in cleaned


def test_frontend_javascript_parses():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is not available on this runner")
    result = subprocess.run(
        [node, "--check", str(ROOT / "frontend/app-v2.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
