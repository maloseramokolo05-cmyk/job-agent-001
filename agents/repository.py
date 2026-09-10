import hashlib
import json
import re

from backend.database import connect, is_integrity_error, now


def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def ingest(job):
    data = job.dict()
    digest = hashlib.sha256((data["description"] + data["requirements"]).encode()).hexdigest()
    values = (
        data.get("vacancy_id"),
        data["title"],
        norm(data["title"]),
        data["company"],
        norm(data["company"]),
        data["location"],
        data["salary"],
        data["date_posted"],
        data["closing_date"],
        data["description"],
        data["requirements"],
        data["source"],
        data["vacancy_url"],
        data["application_url"],
        data.get("application_email", ""),
        data.get("application_method", "WEB"),
        int(bool(data.get("email_verified"))),
        data.get("email_source_url", ""),
        data.get("verified_at"),
        data["work_mode"],
        now(),
        digest,
        "DISCOVERED",
    )
    sql = (
        "INSERT INTO jobs(vacancy_id,title,normalized_title,company,normalized_company,location,salary,"
        "date_posted,closing_date,description,requirements,source,vacancy_url,application_url,"
        "application_email,application_method,email_verified,email_source_url,verified_at,work_mode,"
        "discovered_at,description_hash,status) VALUES(" + ",".join("?" * 23) + ")"
    )
    try:
        with connect() as db:
            cursor = db.execute(sql, values)
            return cursor.lastrowid, False
    except Exception as exc:
        if is_integrity_error(exc):
            return None, True
        raise


def update_analysis(job_id, result, status):
    stored_breakdown = {
        "dimensions": result.get("breakdown", result.get("score_breakdown", {})),
        "evidence": result.get("evidence", {}),
    }
    with connect() as db:
        db.execute(
            "UPDATE jobs SET score=?,classification=?,score_breakdown=?,missing_requirements=?,reasoning=?,status=? WHERE id=?",
            (
                result["score"],
                result["classification"],
                json.dumps(stored_breakdown),
                json.dumps(result.get("missing_requirements", [])),
                result["reasoning"],
                status,
                job_id,
            ),
        )
