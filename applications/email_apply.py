from __future__ import annotations

import hashlib

from agents.documents import generate_cv, read_document
from backend.config import load_preferences, load_profile
from backend.database import connect, event, now, row
from integrations.google.gmail import already_sent_application, send_message


def _body(job, profile):
    name = profile.get("name") or "Tumelo Ramokolo"
    title = job["title"]
    company = job["company"]
    lowered = title.lower()
    if any(word in lowered for word in ("admin", "operations", "coordinator", "customer", "sales support")):
        evidence = (
            "My background includes customer enquiries, project coordination, quotations and proposals, "
            "operational support and business administration, alongside a completed BBA in Marketing."
        )
    elif any(word in lowered for word in ("marketing", "social", "content", "digital", "communication", "crm")):
        evidence = (
            "I hold a completed BBA in Marketing and have practical experience across digital marketing, "
            "social media, content planning, customer engagement, CRM support and campaign activities."
        )
    else:
        evidence = (
            "I hold a completed BBA in Marketing and have practical experience across customer engagement, "
            "business operations, marketing support and project-based client work."
        )
    variants = [
        (
            f"Dear Hiring Team,\n\nI would like to apply for the {title} position at {company}. "
            f"{evidence}\n\nI have attached my CV for your consideration. I would appreciate the opportunity to discuss the role further.\n\n"
            f"Kind regards,\n{name}\n{profile.get('phone', '')}\n{profile.get('email', '')}"
        ),
        (
            f"Dear Hiring Team,\n\nPlease accept my application for the {title} opportunity with {company}. "
            f"{evidence}\n\nMy CV is attached. Thank you for considering my application, and I would be glad to provide any further information required.\n\n"
            f"Kind regards,\n{name}\n{profile.get('phone', '')}\n{profile.get('email', '')}"
        ),
        (
            f"Good day,\n\nI am applying for the advertised {title} role at {company}. {evidence}\n\n"
            f"Please find my CV attached for review. I would welcome the chance to discuss how my experience could support the team.\n\n"
            f"Regards,\n{name}\n{profile.get('phone', '')}\n{profile.get('email', '')}"
        ),
    ]
    selector = int(hashlib.sha256(f"{company}|{title}".encode()).hexdigest()[:4], 16) % len(variants)
    return variants[selector]


def _subject(job, profile):
    name = profile.get("name") or "Tumelo Ramokolo"
    return f"Application: {job['title']} - {name}"


def apply_by_email(job_id: int, master_cv_text: str, *, explicit_authorization: bool = False):
    """Send one application only through a verified email route.

    `explicit_authorization` represents an explicit user-triggered action. Automated scheduled runs
    additionally require AUTO_EMAIL/AUTO_APPLY plus `email_auto_send=true` in preferences.
    """
    job = row("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not job:
        raise ValueError("Job not found")
    preferences = load_preferences()
    profile = load_profile()
    mode = preferences.get("application_mode", "PREPARE")
    allowed = explicit_authorization or (
        mode in {"AUTO_EMAIL", "AUTO_APPLY"} and bool(preferences.get("email_auto_send", False))
    )
    if not allowed:
        raise PermissionError("Automatic email application is not enabled")
    if not job.get("email_verified") or not job.get("application_email") or job.get("application_method") != "EMAIL":
        raise PermissionError("This vacancy does not have a verified published email application route")
    minimum = float(preferences.get("email_minimum_score", 72))
    if float(job.get("score") or 0) < minimum:
        raise PermissionError(f"Job score is below the automatic email threshold ({minimum:g})")
    existing = row(
        "SELECT * FROM applications WHERE job_id=? AND status IN ('APPLIED','APPLIED_CONFIRMED','INTERVIEW','ASSESSMENT','OFFER') ORDER BY id DESC LIMIT 1",
        (job_id,),
    )
    if existing:
        return {"sent": False, "duplicate": True, "reason": "already_tracked", "application_id": existing["id"]}

    duplicate = already_sent_application(
        job["application_email"],
        job["title"],
        job["company"],
        int(preferences.get("email_duplicate_window_days", 365)),
    )
    if duplicate.get("duplicate"):
        with connect() as db:
            db.execute("UPDATE jobs SET status='APPLIED_CONFIRMED' WHERE id=?", (job_id,))
            cursor = db.execute(
                "INSERT INTO applications(job_id,application_date,source,recruiter_email,google_message_id,status,notes,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    job_id,
                    now(),
                    job["source"],
                    job["application_email"],
                    duplicate.get("message_id"),
                    "APPLIED_CONFIRMED",
                    "Duplicate prevented: a matching sent Gmail application already exists.",
                    now(),
                ),
            )
            application_id = cursor.lastrowid
        event("EMAIL_DUPLICATE_PREVENTED", duplicate.get("subject", "Prior application found"), job_id)
        return {"sent": False, "duplicate": True, "reason": "gmail_sent_match", "application_id": application_id}

    if not master_cv_text.strip():
        raise ValueError("Verified master CV text is required before applying")
    _docx_ref, pdf_ref = generate_cv(job, profile, master_cv_text, job_id)
    pdf_bytes, pdf_type, pdf_name = read_document(pdf_ref)
    result = send_message(
        job["application_email"],
        _subject(job, profile),
        _body(job, profile),
        explicit=True,
        attachments=[{"filename": pdf_name, "content": pdf_bytes, "content_type": pdf_type}],
    )
    message_id = result.get("id")
    with connect() as db:
        db.execute("UPDATE jobs SET cv_path=?,status='APPLIED' WHERE id=?", (pdf_ref, job_id))
        cursor = db.execute(
            "INSERT INTO applications(job_id,application_date,cv_version,source,recruiter_email,google_message_id,status,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                job_id,
                now(),
                pdf_ref,
                job["source"],
                job["application_email"],
                message_id,
                "APPLIED",
                f"Verified email application sent using email published on {job.get('email_source_url') or job.get('vacancy_url')}",
                now(),
            ),
        )
        application_id = cursor.lastrowid
    event("EMAIL_APPLICATION_SENT", f"Gmail message {message_id or 'sent'} to {job['application_email']}", job_id)
    return {
        "sent": True,
        "duplicate": False,
        "message_id": message_id,
        "application_id": application_id,
        "recipient": job["application_email"],
        "cv": pdf_ref,
    }
