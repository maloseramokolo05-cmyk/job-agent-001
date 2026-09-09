import os
os.environ["DATABASE_PATH"]="data/test_job_agent.db"
import pytest
from backend.config import ROOT
@pytest.fixture(autouse=True)
def clean_db():
 p=ROOT/"data/test_job_agent.db"
 if p.exists(): p.unlink()
 from backend.database import init_db
 init_db(); yield
 if p.exists(): p.unlink()
