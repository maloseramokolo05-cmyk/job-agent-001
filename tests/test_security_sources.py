import json,socket
import pytest
from backend.security import hash_password,verify_password,validate_public_url
from agents.verification import verify_job
from agents.scoring import score_job
from agents.models import Job
from job_sources.jsonld import JsonLdSource
class Response:
 text='<script type="application/ld+json">{"@type":"JobPosting","title":"Marketing Coordinator","description":"A sufficiently detailed public vacancy description for digital campaigns and content coordination.","datePosted":"2026-01-01","validThrough":"2030-01-01T00:00:00+00:00","hiringOrganization":{"name":"Acme"},"jobLocation":{"address":{"addressLocality":"Pretoria","addressRegion":"Gauteng","addressCountry":"ZA"}},"url":"https://jobs.example.test/1"}</script>'
def test_password_hashing():
 encoded=hash_password("a strong factual passphrase");assert "a strong factual passphrase" not in encoded;assert verify_password("a strong factual passphrase",encoded);assert not verify_password("wrong",encoded)
def test_ssrf_blocks_private(monkeypatch):
 monkeypatch.setattr(socket,"getaddrinfo",lambda *a,**k:[(None,None,None,None,("127.0.0.1",80))])
 with pytest.raises(ValueError):validate_public_url("http://example.test/feed")
def test_ssrf_accepts_public(monkeypatch):
 monkeypatch.setattr(socket,"getaddrinfo",lambda *a,**k:[(None,None,None,None,("8.8.8.8",443))]);assert validate_public_url("https://example.test/jobs")
def test_jsonld_source_fixture(monkeypatch):
 monkeypatch.setattr("job_sources.jsonld.get",lambda url:Response());jobs=JsonLdSource().search({}, {"career_pages":["https://example.test/jobs"]});assert jobs[0].company=="Acme" and jobs[0].location.startswith("Pretoria")
def test_verification_and_hard_requirement():
 job=Job("Analyst","Acme","Pretoria","fixture","https://example.test/job",description="A detailed active vacancy requiring citizenship and extensive reporting capabilities for business teams.",requirements="citizenship reporting")
 assert verify_job(job)["active"]
 result=score_job(job.dict(),{"skills":["reporting"],"experience":[],"education":[],"languages":[]},{"priority_locations":["Pretoria"],"job_categories":["analyst"]});assert not result["must_have"]["passed"]
