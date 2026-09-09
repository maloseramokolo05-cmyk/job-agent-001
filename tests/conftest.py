import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ["DATABASE_PATH"] = "data/test_job_agent.db"

import pytest

from backend.config import ROOT


@pytest.fixture(autouse=True)
def clean_db():
    p = ROOT / "data/test_job_agent.db"
    if p.exists():
        p.unlink()
    from backend.database import init_db

    init_db()
    yield
    if p.exists():
        p.unlink()
