import json
from pathlib import Path
from docx import Document
from agents.models import Job
from agents.repository import ingest
from agents.scoring import score_job,classify
from agents.cv_parser import parse_cv
from agents.parsers import parse_job_html
from agents.documents import generate_cv
from backend.config import load_profile,load_preferences,ROOT
from backend.database import row,connect
from applications.automation import may_submit
from applications.workflow import prepare

def test_duplicate_detection():
 j=Job("Marketing Assistant","Acme","Pretoria","test","https://example.test/1")
 assert ingest(j)[1] is False; assert ingest(j)[1] is True

def test_scoring_and_classification():
 job={"title":"Digital Marketing Coordinator","description":"social media content","requirements":"digital marketing communication","location":"Pretoria","salary":"","work_mode":"hybrid"}
 result=score_job(job,{"skills":["digital marketing","social media","communication"],"experience":[],"education":[]},{"priority_locations":["Pretoria"],"job_categories":["Marketing"]},"content campaigns")
 assert 0<=result["score"]<=100; assert sum(result["breakdown"].values())==result["score"]; assert classify(90)=="Excellent Match"

def test_cv_parser_docx(tmp_path):
 p=tmp_path/"cv.docx"; d=Document(); d.add_paragraph("Factual experience"); d.save(p); assert "Factual experience" in parse_cv(p)

def test_job_parser():
 j=parse_job_html('<main><h1>Coordinator</h1><div class="company">Acme</div><div class="location">Midrand</div><p>Work here</p></main>',"https://x.test")
 assert j.title=="Coordinator" and j.company=="Acme" and "Work here" in j.description

def test_status_change_storage():
 j=Job("Role","Firm","Gauteng","test","https://example.test/status"); jid,_=ingest(j)
 with connect() as db: db.execute("UPDATE jobs SET status='INTERVIEW' WHERE id=?",(jid,))
 assert row("SELECT status FROM jobs WHERE id=?",(jid,))["status"]=="INTERVIEW"

def test_document_generation(tmp_path):
 job={"company":"Acme","title":"Coordinator"}; profile={"name":"Tumelo Ramokolo","email":"","phone":"","location":"Gauteng","linkedin":""}
 docx,pdf=generate_cv(job,profile,"Verified skill\nVerified employer")
 assert (ROOT/docx).exists(); (ROOT/docx).unlink()
 if pdf: assert (ROOT/pdf).exists(); (ROOT/pdf).unlink()

def test_configuration_loading():
 assert load_profile()["name"]=="Tumelo Ramokolo"; assert load_preferences()["application_mode"]=="PREPARE"

def test_application_submission_requires_explicit_opt_in():
 assert may_submit(explicit_confirmation=True) is False

def test_application_package_stops_for_unknown_facts():
 package=prepare({"application_url":"https://example.test/apply","cv_path":"generated_cvs/cv.docx"},{"name":"Tumelo","email":"","phone":"","location":"Gauteng"},[{"question":"Do you hold licence X?","required":True}])
 assert not package["ready"] and "email" in package["missing_profile_fields"] and package["unanswered_questions"]
