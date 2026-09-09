from docx import Document

from agents.cv_parser import parse_cv
from agents.documents import generate_cv, read_document
from agents.models import Job
from agents.parsers import parse_job_html
from agents.repository import ingest
from agents.scoring import classify, score_job
from applications.automation import may_submit
from backend.config import load_preferences, load_profile
from backend.database import connect, row


def test_duplicate_detection():
    job = Job("Marketing Assistant", "Acme", "Pretoria", "test", "https://example.test/1")
    assert ingest(job)[1] is False
    assert ingest(job)[1] is True


def test_scoring_and_classification():
    job = {
        "title": "Digital Marketing Coordinator",
        "description": "social media content",
        "requirements": "digital marketing communication",
        "location": "Pretoria",
        "salary": "",
        "work_mode": "hybrid",
    }
    result = score_job(
        job,
        {"skills": ["digital marketing", "social media", "communication"], "experience": [], "education": []},
        {"priority_locations": ["Pretoria"], "job_categories": ["Marketing"]},
        "content campaigns",
    )
    assert 0 <= result["score"] <= 100
    assert sum(result["breakdown"].values()) == result["score"]
    assert classify(90) == "Excellent Match"


def test_cv_parser_docx(tmp_path):
    path = tmp_path / "cv.docx"
    document = Document()
    document.add_paragraph("Factual experience")
    document.save(path)
    assert "Factual experience" in parse_cv(path)


def test_job_parser():
    job = parse_job_html(
        '<main><h1>Coordinator</h1><div class="company">Acme</div><div class="location">Midrand</div><p>Work here</p></main>',
        "https://x.test",
    )
    assert job.title == "Coordinator" and job.company == "Acme" and "Work here" in job.description


def test_status_change_storage():
    job = Job("Role", "Firm", "Gauteng", "test", "https://example.test/status")
    job_id, _ = ingest(job)
    with connect() as db:
        db.execute("UPDATE jobs SET status='INTERVIEW' WHERE id=?", (job_id,))
    assert row("SELECT status FROM jobs WHERE id=?", (job_id,))["status"] == "INTERVIEW"


def test_document_generation_uses_private_storage():
    job = {"company": "Acme", "title": "Coordinator", "description": "coordination", "requirements": "coordination"}
    profile = {"name": "Tumelo Ramokolo", "email": "", "phone": "", "location": "Gauteng", "linkedin": ""}
    docx_ref, pdf_ref = generate_cv(job, profile, "Verified skill\nVerified employer")
    assert docx_ref.startswith("storage:") and pdf_ref.startswith("storage:")
    docx_bytes, docx_type, _ = read_document(docx_ref)
    pdf_bytes, pdf_type, _ = read_document(pdf_ref)
    assert docx_bytes.startswith(b"PK")
    assert docx_type.startswith("application/vnd.openxmlformats")
    assert pdf_bytes.startswith(b"%PDF") and pdf_type == "application/pdf"


def test_configuration_loading():
    assert load_profile()["name"] == "Tumelo Ramokolo"
    assert load_preferences()["application_mode"] == "AUTO_EMAIL"


def test_application_submission_requires_explicit_opt_in():
    # Browser-form automation remains disabled by AUTO_EMAIL; only verified email routes use the email service.
    assert may_submit(explicit_confirmation=True) is False
