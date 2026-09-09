import base64
from email import message_from_bytes

from agents.models import Job
from agents.repository import ingest
from applications import email_apply
from backend.database import connect, row
from integrations.google.gmail import build_message
from job_sources.email_extract import extract_application_email


def test_application_email_requires_application_context():
    email, evidence = extract_application_email(
        "To apply, please email your CV to recruitment@example.co.za before Friday."
    )
    assert email == "recruitment@example.co.za"
    assert "apply" in evidence.lower()
    assert extract_application_email("For privacy questions contact privacy@example.co.za")[0] is None


def test_gmail_message_can_attach_pdf():
    raw = build_message(
        "jobs@example.co.za",
        "Application: Marketing Assistant - Tumelo Ramokolo",
        "Dear Hiring Team,\n\nPlease find my CV attached.",
        attachments=[{"filename": "Tumelo Ramokolo - Marketing Assistant - CV.pdf", "content": b"%PDF-test", "content_type": "application/pdf"}],
    )
    message = message_from_bytes(base64.urlsafe_b64decode(raw.encode()))
    attachments = list(message.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename().endswith("CV.pdf")
    assert attachments[0].get_payload(decode=True) == b"%PDF-test"


def test_verified_email_application_tracks_send(monkeypatch):
    job = Job(
        "Marketing Assistant",
        "Acme SA",
        "Pretoria",
        "test",
        "https://example.test/job-email",
        description="Marketing support",
        requirements="digital marketing social media",
        application_url="https://example.test/job-email",
        application_email="jobs@acme.example",
        application_method="EMAIL",
        email_verified=True,
        email_source_url="https://example.test/job-email",
    )
    job_id, duplicate = ingest(job)
    assert not duplicate
    with connect() as db:
        db.execute("UPDATE jobs SET score=90,status='SHORTLISTED' WHERE id=?", (job_id,))
    monkeypatch.setattr(email_apply, "already_sent_application", lambda *args, **kwargs: {"duplicate": False})
    monkeypatch.setattr(email_apply, "send_message", lambda *args, **kwargs: {"id": "gmail-message-123"})
    result = email_apply.apply_by_email(job_id, "Verified master CV fact\nBBA Marketing", explicit_authorization=True)
    assert result["sent"] is True
    assert result["message_id"] == "gmail-message-123"
    assert row("SELECT status FROM jobs WHERE id=?", (job_id,))["status"] == "APPLIED"
    application = row("SELECT * FROM applications WHERE job_id=?", (job_id,))
    assert application["recruiter_email"] == "jobs@acme.example"
    assert application["google_message_id"] == "gmail-message-123"
