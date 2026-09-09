from __future__ import annotations
import json, sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from .config import database_path
SCHEMA="""
CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, vacancy_id TEXT, title TEXT NOT NULL, normalized_title TEXT NOT NULL, company TEXT NOT NULL, normalized_company TEXT NOT NULL, location TEXT DEFAULT '', salary TEXT DEFAULT '', date_posted TEXT, closing_date TEXT, description TEXT DEFAULT '', requirements TEXT DEFAULT '', source TEXT NOT NULL, vacancy_url TEXT DEFAULT '', application_url TEXT DEFAULT '', work_mode TEXT DEFAULT '', discovered_at TEXT NOT NULL, description_hash TEXT NOT NULL, score REAL, classification TEXT, score_breakdown TEXT DEFAULT '{}', missing_requirements TEXT DEFAULT '[]', reasoning TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'FOUND', cv_path TEXT, cover_letter_path TEXT, unanswered_question TEXT, UNIQUE(source, vacancy_id), UNIQUE(vacancy_url), UNIQUE(normalized_title, normalized_company, location));
CREATE TABLE IF NOT EXISTS applications(id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL, application_date TEXT, cv_version TEXT, source TEXT, contact_person TEXT, recruiter_email TEXT, status TEXT NOT NULL, interview_dates TEXT, notes TEXT, salary TEXT, follow_up_date TEXT, answers TEXT DEFAULT '{}', screenshot_path TEXT, created_at TEXT NOT NULL, FOREIGN KEY(job_id) REFERENCES jobs(id));
CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, state TEXT NOT NULL, progress INTEGER DEFAULT 0, message TEXT DEFAULT '', stats TEXT DEFAULT '{}');
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, job_id INTEGER, event_type TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
def now(): return datetime.now(timezone.utc).isoformat()
@contextmanager
def connect():
 p=database_path(); p.parent.mkdir(parents=True, exist_ok=True); db=sqlite3.connect(p, timeout=30); db.row_factory=sqlite3.Row; db.execute("PRAGMA foreign_keys=ON")
 try: yield db; db.commit()
 finally: db.close()
def init_db():
 with connect() as db: db.executescript(SCHEMA)
def rows(sql, args=()):
 with connect() as db: return [dict(x) for x in db.execute(sql,args).fetchall()]
def row(sql,args=()):
 with connect() as db:
  x=db.execute(sql,args).fetchone(); return dict(x) if x else None
def execute(sql,args=()):
 with connect() as db: cur=db.execute(sql,args); return cur.lastrowid
def event(kind, detail, job_id=None): execute("INSERT INTO events(job_id,event_type,detail,created_at) VALUES(?,?,?,?)",(job_id,kind,detail,now()))
