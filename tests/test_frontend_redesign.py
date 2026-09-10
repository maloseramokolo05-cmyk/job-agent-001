from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app-v2.js").read_text(encoding="utf-8")
CSS = (
    (ROOT / "frontend/style.css").read_text(encoding="utf-8")
    + (ROOT / "frontend/product.css").read_text(encoding="utf-8")
)


def test_redesigned_shell_keeps_core_views_and_auth_controls():
    for element_id in [
        "dashboard",
        "jobs",
        "applications",
        "documents",
        "profile",
        "integrations",
        "settings",
        "diagnostics",
        "loginDialog",
        "googleLogin",
        "uploadGoogleCredentials",
        "run",
        "notificationButton",
        "profileButton",
    ]:
        assert f'id="{element_id}"' in INDEX


def test_frontend_keeps_existing_job_agent_api_contracts_and_product_endpoints():
    for route in [
        "/api/jobs",
        "/api/applications",
        "/api/cv",
        "/api/google/status",
        "/api/google/connect",
        "/api/gmail/sync",
        "/api/runs",
        "/api/runs/latest",
        "/api/setup",
        "/api/settings",
        "/api/dashboard",
        "/api/actions",
        "/api/inbox",
        "/api/document-groups",
        "/api/diagnostics",
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
    assert "loadDashboard()" in APP
    assert "renderActions(actionsCache)" in APP
    assert "renderTopMatches(jobsResult.value)" in APP
    for mock_name in ["Absa Group", "Microsoft South Africa", "Discovery Limited", "FNB"]:
        assert mock_name not in INDEX
        assert mock_name not in APP


def test_search_progress_is_visible_before_synchronous_run_request_finishes():
    run_function = APP.split("function runSearch()", 1)[1].split("async function loadJobs", 1)[0]
    assert run_function.index("showRunProgress()") < run_function.index("api('/api/runs'")
    assert "setTimeout(pollRun,500)" in run_function


def test_dashboard_loads_components_resiliently():
    assert "Promise.allSettled" in APP
    assert "Couldn’t load this section" in APP
