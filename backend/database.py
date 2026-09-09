from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from .config import database_path
LATEST_SCHEMA_VERSION = 2
BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, vacancy_id TEXT, title TEXT NOT NULL, normalized_title TEXT NOT NULL, company TEXT NOT NULL, normalized_company TEXT NOT NULL, location TEXT DEFAULT '', salary TEXT DEFAULT '', date_posted TEXT, closing_date TEXT, description TEXT DEFAULT '', requirements TEXT DEFAULT '', source TEXT NOT NULL, vacancy_url TEXT DEFAULT '', application_url TEXT DEFAULT '', work_mode TEXT DEFAULT '', discovered_at TEXT NOT NULL, description_hash TEXT NOT NULL, score REAL, classification TEXT, score_breakdown TEXT DEFAULT '{}', missing_requirements TEXT DEFAULT '[]', reasoning TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'DISCOVERED', cv_path TEXT, cover_letter_path TEXT, unanswered_question TEXT, priority REAL DEFAULT 0, UNIQUE(source, vacancy_id), UNIQUE(vacancy_url), UNIQUE(normalized_title, normalized_company, location));
CREATE TABLE IF NOT EXISTS applications(id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL, application_date TEXT, cv_version TEXT, source TEXT, contact_person TEXT, recruiter_email TEXT, status TEXT NOT NULL, interview_dates TEXT, notes TEXT, salary TEXT, follow_up_date TEXT, answers TEXT DEFAULT '{}', screenshot_path TEXT, created_at TEXT NOT NULL, FOREIGN KEY(job_id) REFERENCES jobs(id));
CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY, job_id INTEGER, document_type TEXT NOT NULL, local_path TEXT NOT NULL, created_at TEXT NOT NULL, master_cv_hash TEXT, template_version TEXT, generator_version TEXT, drive_file_id TEXT, content_hash TEXT, FOREIGN KEY(job_id) REFERENCES jobs(id));
CREATE TABLE IF NOT EXISTS emails(id INTEGER PRIMARY KEY, google_message_id TEXT UNIQUE, thread_id TEXT, sender TEXT, subject TEXT, received_at TEXT, classification TEXT NOT NULL, confidence REAL DEFAULT 0, related_job_id INTEGER, action_required INTEGER DEFAULT 0, response_status TEXT DEFAULT 'UNREAD', snippet TEXT, FOREIGN KEY(related_job_id) REFERENCES jobs(id));
CREATE TABLE IF NOT EXISTS google_accounts(id INTEGER PRIMARY KEY, email TEXT, status TEXT NOT NULL DEFAULT 'DISCONNECTED', scopes TEXT DEFAULT '[]', last_gmail_sync TEXT, last_drive_sync TEXT, last_calendar_sync TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS calendar_events(id INTEGER PRIMARY KEY, google_event_id TEXT UNIQUE, job_id INTEGER, source_thread_id TEXT, event_type TEXT NOT NULL, starts_at TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(job_id,source_thread_id,starts_at), FOREIGN KEY(job_id) REFERENCES jobs(id));
CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, state TEXT NOT NULL, progress INTEGER DEFAULT 0, message TEXT DEFAULT '', stats TEXT DEFAULT '{}', checkpoint TEXT DEFAULT '{}');
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, job_id INTEGER, run_id INTEGER, event_type TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_status(source_name TEXT PRIMARY KEY, supported INTEGER NOT NULL, authenticated INTEGER NOT NULL, search_supported INTEGER NOT NULL, application_supported INTEGER NOT NULL, status TEXT NOT NULL, last_success TEXT, last_error TEXT);
CREATE TABLE IF NOT EXISTS oauth_state(state TEXT PRIMARY KEY, code_verifier TEXT NOT NULL, redirect_uri TEXT NOT NULL, scopes TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_jobs_status_score ON jobs(status,score DESC);
CREATE INDEX IF NOT EXISTS idx_emails_classification ON emails(classification,received_at DESC);
"""
def now(): return datetime.now(timezone.utc).isoformat()
@contextmanager
def connect():
 p=database_path(); p.parent.mkdir(parents=True,exist_ok=True); db=sqlite3.connect(p,timeout=30); db.row_factory=sqlite3.Row; db.execute("PRAGMA foreign_keys=ON"); db.execute("PRAGMA journal_mode=WAL")
 try: yield db; db.commit()
 finally: db.close()
def _column(db,table,name,definition):
 names={r[1] for r in db.execute(f"PRAGMA table_info({table})")}
 if name not in names: db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
def migrate():
 with connect() as db:
  db.executescript(BASE_SCHEMA)
  # Upgrade databases created by 1.x without deleting history.
  _column(db,"jobs","priority","REAL DEFAULT 0")
  _column(db,"runs","checkpoint","TEXT DEFAULT '{}'")
  _column(db,"events","run_id","INTEGER")
  db.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(?,?)",(1,now()))
  db.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(?,?)",(2,now()))
  db.execute("UPDATE runs SET state='INTERRUPTED', finished_at=? WHERE state='RUNNING'",(now(),))
def init_db(): migrate()
def schema_version():
 with connect() as db:
  row=db.execute("SELECT MAX(version) FROM schema_migrations").fetchone(); return int(row[0] or 0)
def rows(sql,args=()):
 with connect() as db:return [dict(x) for x in db.execute(sql,args).fetchall()]
def row(sql,args=()):
 with connect() as db:
  x=db.execute(sql,args).fetchone(); return dict(x) if x else None
def execute(sql,args=()):
 with connect() as db:cur=db.execute(sql,args); return cur.lastrowid
def event(kind,detail,job_id=None,run_id=None): execute("INSERT INTO events(job_id,run_id,event_type,detail,created_at) VALUES(?,?,?,?,?)",(job_id,run_id,kind,detail,now()))
