from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
CSS = (ROOT / "frontend/style.css").read_text(encoding="utf-8")


def test_redesigned_shell_keeps_core_views_and_auth_controls():
    for element_id in [
        "dashboard",
        "jobs",
        "applications",
        "documents",
        "profile",
        "google",
        "sources",
        "settings",
        "logs",
        "loginDialog",
        "googleLogin",
        "uploadGoogleCredentials",
        "run",
    ]:
        assert f'id="{element_id}"' in INDEX


def test_frontend_keeps_existing_job_agent_api_contracts():
    for route in [
        "/api/overview",
        "/api/jobs",
        "/api/applications",
        "/api/documents",
        "/api/cv",
        "/api/google/status",
        "/api/google/connect",
        "/api/gmail/sync",
        "/api/sources",
        "/api/config",
        "/api/logs",
        "/api/runs",
        "/api/runs/latest",
        "/api/setup",
    ]:
        assert route in APP


def test_mobile_ui_has_bottom_navigation_and_safe_responsive_rules():
    assert 'class="mobile-nav"' in INDEX
    for label in [">Home<", ">Jobs<", ">Applications<", ">Profile<"]:
        assert label in INDEX
    assert "@media(max-width:767px)" in CSS
    assert "env(safe-area-inset-bottom)" in CSS
    assert "overflow-x:hidden" in CSS
    assert "min-height:44px" in CSS


def test_dashboard_uses_real_api_values_not_mock_company_content():
    assert "renderMetrics(m)" in APP
    assert "renderCompactJobs(jobs)" in APP
    assert "renderPipeline(m)" in APP
    for mock_name in ["Absa Group", "Microsoft South Africa", "Discovery Limited", "FNB"]:
        assert mock_name not in INDEX
        assert mock_name not in APP
