from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import database_path

LATEST_SCHEMA_VERSION = 4
ID_TABLES = {
    "users", "sessions", "candidate_profiles", "candidate_profile_versions", "master_cvs",
    "audit_events", "jobs", "applications", "documents", "emails", "google_accounts",
    "calendar_events", "runs", "events",
}

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, username TEXT NOT NULL, expires_at TEXT NOT NULL, revoked_at TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token_hash,expires_at);
CREATE TABLE IF NOT EXISTS candidate_profiles(id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, profile_json TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS candidate_profile_versions(id INTEGER PRIMARY KEY, username TEXT NOT NULL, version INTEGER NOT NULL, profile_json TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(username,version));
CREATE TABLE IF NOT EXISTS master_cvs(id INTEGER PRIMARY KEY, username TEXT NOT NULL, version INTEGER NOT NULL, storage_key TEXT NOT NULL, sha256 TEXT NOT NULL, content_type TEXT NOT NULL, original_name TEXT NOT NULL, extracted_text TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(username,version));
CREATE TABLE IF NOT EXISTS audit_events(id INTEGER PRIMARY KEY, username TEXT, event_type TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, vacancy_id TEXT, title TEXT NOT NULL, normalized_title TEXT NOT NULL, company TEXT NOT NULL, normalized_company TEXT NOT NULL, location TEXT DEFAULT '', salary TEXT DEFAULT '', date_posted TEXT, closing_date TEXT, description TEXT DEFAULT '', requirements TEXT DEFAULT '', source TEXT NOT NULL, vacancy_url TEXT DEFAULT '', application_url TEXT DEFAULT '', application_email TEXT DEFAULT '', application_method TEXT DEFAULT 'WEB', email_verified INTEGER DEFAULT 0, email_source_url TEXT DEFAULT '', verified_at TEXT, work_mode TEXT DEFAULT '', discovered_at TEXT NOT NULL, description_hash TEXT NOT NULL, score REAL, classification TEXT, score_breakdown TEXT DEFAULT '{}', missing_requirements TEXT DEFAULT '[]', reasoning TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'DISCOVERED', cv_path TEXT, cover_letter_path TEXT, unanswered_question TEXT, priority REAL DEFAULT 0, UNIQUE(source, vacancy_id), UNIQUE(vacancy_url), UNIQUE(normalized_title, normalized_company, location));
CREATE TABLE IF NOT EXISTS applications(id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL, application_date TEXT, cv_version TEXT, source TEXT, contact_person TEXT, recruiter_email TEXT, google_message_id TEXT, status TEXT NOT NULL, interview_dates TEXT, notes TEXT, salary TEXT, follow_up_date TEXT, answers TEXT DEFAULT '{}', screenshot_path TEXT, created_at TEXT NOT NULL, FOREIGN KEY(job_id) REFERENCES jobs(id));
CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY, job_id INTEGER, document_type TEXT NOT NULL, local_path TEXT NOT NULL DEFAULT '', storage_key TEXT DEFAULT '', content_type TEXT DEFAULT '', created_at TEXT NOT NULL, master_cv_hash TEXT, template_version TEXT, generator_version TEXT, drive_file_id TEXT, content_hash TEXT, FOREIGN KEY(job_id) REFERENCES jobs(id));
CREATE TABLE IF NOT EXISTS emails(id INTEGER PRIMARY KEY, google_message_id TEXT UNIQUE, thread_id TEXT, sender TEXT, subject TEXT, received_at TEXT, classification TEXT NOT NULL, confidence REAL DEFAULT 0, related_job_id INTEGER, action_required INTEGER DEFAULT 0, response_status TEXT DEFAULT 'UNREAD', snippet TEXT, FOREIGN KEY(related_job_id) REFERENCES jobs(id));
CREATE TABLE IF NOT EXISTS google_accounts(id INTEGER PRIMARY KEY, email TEXT, status TEXT NOT NULL DEFAULT 'DISCONNECTED', scopes TEXT DEFAULT '[]', last_gmail_sync TEXT, last_drive_sync TEXT, last_calendar_sync TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS calendar_events(id INTEGER PRIMARY KEY, google_event_id TEXT UNIQUE, job_id INTEGER, source_thread_id TEXT, event_type TEXT NOT NULL, starts_at TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(job_id,source_thread_id,starts_at), FOREIGN KEY(job_id) REFERENCES jobs(id));
CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, state TEXT NOT NULL, progress INTEGER DEFAULT 0, message TEXT DEFAULT '', stats TEXT DEFAULT '{}', checkpoint TEXT DEFAULT '{}');
CREATE UNIQUE INDEX IF NOT EXISTS idx_runs_one_active ON runs(state) WHERE state='RUNNING';
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, job_id INTEGER, run_id INTEGER, event_type TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_status(source_name TEXT PRIMARY KEY, supported INTEGER NOT NULL, authenticated INTEGER NOT NULL, search_supported INTEGER NOT NULL, application_supported INTEGER NOT NULL, status TEXT NOT NULL, last_success TEXT, last_error TEXT);
CREATE TABLE IF NOT EXISTS oauth_state(state TEXT PRIMARY KEY, code_verifier TEXT NOT NULL, redirect_uri TEXT NOT NULL, scopes TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS file_objects(storage_key TEXT PRIMARY KEY, content_type TEXT NOT NULL, sha256 TEXT NOT NULL, content BLOB NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_jobs_status_score ON jobs(status,score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_email ON jobs(email_verified,application_email);
CREATE INDEX IF NOT EXISTS idx_emails_classification ON emails(classification,received_at DESC);
"""

POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users(id BIGSERIAL PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(id BIGSERIAL PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, username TEXT NOT NULL, expires_at TEXT NOT NULL, revoked_at TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token_hash,expires_at);
CREATE TABLE IF NOT EXISTS candidate_profiles(id BIGSERIAL PRIMARY KEY, username TEXT NOT NULL UNIQUE, profile_json TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS candidate_profile_versions(id BIGSERIAL PRIMARY KEY, username TEXT NOT NULL, version INTEGER NOT NULL, profile_json TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(username,version));
CREATE TABLE IF NOT EXISTS master_cvs(id BIGSERIAL PRIMARY KEY, username TEXT NOT NULL, version INTEGER NOT NULL, storage_key TEXT NOT NULL, sha256 TEXT NOT NULL, content_type TEXT NOT NULL, original_name TEXT NOT NULL, extracted_text TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(username,version));
CREATE TABLE IF NOT EXISTS audit_events(id BIGSERIAL PRIMARY KEY, username TEXT, event_type TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(id BIGSERIAL PRIMARY KEY, vacancy_id TEXT, title TEXT NOT NULL, normalized_title TEXT NOT NULL, company TEXT NOT NULL, normalized_company TEXT NOT NULL, location TEXT DEFAULT '', salary TEXT DEFAULT '', date_posted TEXT, closing_date TEXT, description TEXT DEFAULT '', requirements TEXT DEFAULT '', source TEXT NOT NULL, vacancy_url TEXT DEFAULT '', application_url TEXT DEFAULT '', application_email TEXT DEFAULT '', application_method TEXT DEFAULT 'WEB', email_verified INTEGER DEFAULT 0, email_source_url TEXT DEFAULT '', verified_at TEXT, work_mode TEXT DEFAULT '', discovered_at TEXT NOT NULL, description_hash TEXT NOT NULL, score DOUBLE PRECISION, classification TEXT, score_breakdown TEXT DEFAULT '{}', missing_requirements TEXT DEFAULT '[]', reasoning TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'DISCOVERED', cv_path TEXT, cover_letter_path TEXT, unanswered_question TEXT, priority DOUBLE PRECISION DEFAULT 0, UNIQUE(source, vacancy_id), UNIQUE(vacancy_url), UNIQUE(normalized_title, normalized_company, location));
CREATE TABLE IF NOT EXISTS applications(id BIGSERIAL PRIMARY KEY, job_id BIGINT NOT NULL REFERENCES jobs(id), application_date TEXT, cv_version TEXT, source TEXT, contact_person TEXT, recruiter_email TEXT, google_message_id TEXT, status TEXT NOT NULL, interview_dates TEXT, notes TEXT, salary TEXT, follow_up_date TEXT, answers TEXT DEFAULT '{}', screenshot_path TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents(id BIGSERIAL PRIMARY KEY, job_id BIGINT REFERENCES jobs(id), document_type TEXT NOT NULL, local_path TEXT NOT NULL DEFAULT '', storage_key TEXT DEFAULT '', content_type TEXT DEFAULT '', created_at TEXT NOT NULL, master_cv_hash TEXT, template_version TEXT, generator_version TEXT, drive_file_id TEXT, content_hash TEXT);
CREATE TABLE IF NOT EXISTS emails(id BIGSERIAL PRIMARY KEY, google_message_id TEXT UNIQUE, thread_id TEXT, sender TEXT, subject TEXT, received_at TEXT, classification TEXT NOT NULL, confidence DOUBLE PRECISION DEFAULT 0, related_job_id BIGINT REFERENCES jobs(id), action_required INTEGER DEFAULT 0, response_status TEXT DEFAULT 'UNREAD', snippet TEXT);
CREATE TABLE IF NOT EXISTS google_accounts(id BIGSERIAL PRIMARY KEY, email TEXT, status TEXT NOT NULL DEFAULT 'DISCONNECTED', scopes TEXT DEFAULT '[]', last_gmail_sync TEXT, last_drive_sync TEXT, last_calendar_sync TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS calendar_events(id BIGSERIAL PRIMARY KEY, google_event_id TEXT UNIQUE, job_id BIGINT REFERENCES jobs(id), source_thread_id TEXT, event_type TEXT NOT NULL, starts_at TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(job_id,source_thread_id,starts_at));
CREATE TABLE IF NOT EXISTS runs(id BIGSERIAL PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, state TEXT NOT NULL, progress INTEGER DEFAULT 0, message TEXT DEFAULT '', stats TEXT DEFAULT '{}', checkpoint TEXT DEFAULT '{}');
CREATE UNIQUE INDEX IF NOT EXISTS idx_runs_one_active ON runs(state) WHERE state='RUNNING';
CREATE TABLE IF NOT EXISTS events(id BIGSERIAL PRIMARY KEY, job_id BIGINT, run_id BIGINT, event_type TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_status(source_name TEXT PRIMARY KEY, supported INTEGER NOT NULL, authenticated INTEGER NOT NULL, search_supported INTEGER NOT NULL, application_supported INTEGER NOT NULL, status TEXT NOT NULL, last_success TEXT, last_error TEXT);
CREATE TABLE IF NOT EXISTS oauth_state(state TEXT PRIMARY KEY, code_verifier TEXT NOT NULL, redirect_uri TEXT NOT NULL, scopes TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS file_objects(storage_key TEXT PRIMARY KEY, content_type TEXT NOT NULL, sha256 TEXT NOT NULL, content BYTEA NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_jobs_status_score ON jobs(status,score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_email ON jobs(email_verified,application_email);
CREATE INDEX IF NOT EXISTS idx_emails_classification ON emails(classification,received_at DESC);
"""


def now():
    return datetime.now(timezone.utc).isoformat()


def using_postgres() -> bool:
    return os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql://"))


class HybridRow(Mapping):
    def __init__(self, columns, values):
        self._columns = tuple(columns)
        self._values = tuple(values)
        self._map = dict(zip(self._columns, self._values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._map[key]

    def __iter__(self):
        return iter(self._map)

    def __len__(self):
        return len(self._values)

    def keys(self):
        return self._map.keys()


class PgCursor:
    def __init__(self, cursor, *, lastrowid=None):
        self.cursor = cursor
        self.lastrowid = lastrowid
        self.rowcount = cursor.rowcount
        self._columns = [item.name if hasattr(item, "name") else item[0] for item in (cursor.description or [])]

    def _wrap(self, value):
        return None if value is None else HybridRow(self._columns, value)

    def fetchone(self):
        return self._wrap(self.cursor.fetchone())

    def fetchall(self):
        return [self._wrap(value) for value in self.cursor.fetchall()]

    def __iter__(self):
        for value in self.cursor:
            yield self._wrap(value)


class PgConnection:
    def __init__(self, connection):
        self.connection = connection

    @staticmethod
    def _sql(sql: str) -> str:
        return sql.replace("?", "%s")

    def execute(self, sql, args=()):
        statement = self._sql(sql)
        insert = re.match(r"\s*INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)", statement, re.I)
        wants_id = bool(insert and insert.group(1).lower() in ID_TABLES and " returning " not in statement.lower())
        if wants_id:
            statement = statement.rstrip().rstrip(";") + " RETURNING id"
        cursor = self.connection.cursor()
        cursor.execute(statement, args)
        lastrowid = None
        if wants_id:
            returned = cursor.fetchone()
            lastrowid = returned[0] if returned else None
        return PgCursor(cursor, lastrowid=lastrowid)

    def executescript(self, script):
        for statement in [item.strip() for item in script.split(";") if item.strip()]:
            self.execute(statement)


@contextmanager
def connect():
    if using_postgres():
        import psycopg

        raw = psycopg.connect(os.environ["DATABASE_URL"])
        db = PgConnection(raw)
        try:
            yield db
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.close()
        return

    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")
    try:
        yield db
        db.commit()
    finally:
        db.close()


def _sqlite_column(db, table, name, definition):
    names = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
    if name not in names:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _postgres_columns():
    with connect() as db:
        additions = {
            "jobs": {
                "application_email": "TEXT DEFAULT ''", "application_method": "TEXT DEFAULT 'WEB'",
                "email_verified": "INTEGER DEFAULT 0", "email_source_url": "TEXT DEFAULT ''", "verified_at": "TEXT",
                "priority": "DOUBLE PRECISION DEFAULT 0",
            },
            "applications": {"google_message_id": "TEXT"},
            "documents": {"storage_key": "TEXT DEFAULT ''", "content_type": "TEXT DEFAULT ''"},
            "runs": {"checkpoint": "TEXT DEFAULT '{}'"},
            "events": {"run_id": "BIGINT"},
        }
        for table, columns in additions.items():
            for name, definition in columns.items():
                db.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {definition}")


def migrate():
    if using_postgres():
        with connect() as db:
            db.executescript(POSTGRES_SCHEMA)
        _postgres_columns()
        with connect() as db:
            for version in range(1, LATEST_SCHEMA_VERSION + 1):
                db.execute(
                    "INSERT INTO schema_migrations(version,applied_at) VALUES(?,?) ON CONFLICT(version) DO NOTHING",
                    (version, now()),
                )
        return

    with connect() as db:
        db.executescript(SQLITE_SCHEMA)
        _sqlite_column(db, "jobs", "priority", "REAL DEFAULT 0")
        _sqlite_column(db, "jobs", "application_email", "TEXT DEFAULT ''")
        _sqlite_column(db, "jobs", "application_method", "TEXT DEFAULT 'WEB'")
        _sqlite_column(db, "jobs", "email_verified", "INTEGER DEFAULT 0")
        _sqlite_column(db, "jobs", "email_source_url", "TEXT DEFAULT ''")
        _sqlite_column(db, "jobs", "verified_at", "TEXT")
        _sqlite_column(db, "applications", "google_message_id", "TEXT")
        _sqlite_column(db, "documents", "storage_key", "TEXT DEFAULT ''")
        _sqlite_column(db, "documents", "content_type", "TEXT DEFAULT ''")
        _sqlite_column(db, "runs", "checkpoint", "TEXT DEFAULT '{}'")
        _sqlite_column(db, "events", "run_id", "INTEGER")
        for version in range(1, LATEST_SCHEMA_VERSION + 1):
            db.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(?,?)", (version, now()))


def init_db():
    migrate()


def schema_version():
    with connect() as db:
        value = db.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
        return int(value[0] or 0)


def rows(sql, args=()):
    with connect() as db:
        return [dict(item) for item in db.execute(sql, args).fetchall()]


def row(sql, args=()):
    with connect() as db:
        item = db.execute(sql, args).fetchone()
        return dict(item) if item else None


def execute(sql, args=()):
    with connect() as db:
        cursor = db.execute(sql, args)
        return cursor.lastrowid


def is_integrity_error(exc: Exception) -> bool:
    if isinstance(exc, sqlite3.IntegrityError):
        return True
    if using_postgres():
        try:
            import psycopg
            return isinstance(exc, psycopg.IntegrityError)
        except ImportError:
            return False
    return False


def put_blob(storage_key: str, content_type: str, sha256: str, content: bytes):
    with connect() as db:
        if using_postgres():
            db.execute(
                "INSERT INTO file_objects(storage_key,content_type,sha256,content,created_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(storage_key) DO UPDATE SET content_type=EXCLUDED.content_type, sha256=EXCLUDED.sha256, content=EXCLUDED.content, created_at=EXCLUDED.created_at",
                (storage_key, content_type, sha256, content, now()),
            )
        else:
            db.execute(
                "INSERT OR REPLACE INTO file_objects(storage_key,content_type,sha256,content,created_at) VALUES(?,?,?,?,?)",
                (storage_key, content_type, sha256, content, now()),
            )


def get_blob(storage_key: str):
    with connect() as db:
        item = db.execute(
            "SELECT content_type,sha256,content FROM file_objects WHERE storage_key=?", (storage_key,)
        ).fetchone()
        if not item:
            return None
        return {"content_type": item[0], "sha256": item[1], "content": bytes(item[2])}


def event(kind, detail, job_id=None, run_id=None):
    execute(
        "INSERT INTO events(job_id,run_id,event_type,detail,created_at) VALUES(?,?,?,?,?)",
        (job_id, run_id, kind, detail, now()),
    )
