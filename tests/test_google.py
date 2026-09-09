import json,time
from pathlib import Path
import pytest
from backend.database import connect
from integrations.google.token_store import TokenStore
from integrations.google import oauth,gmail,drive,calendar
class Response:
 def __init__(self,data):self.data=data
 def json(self):return self.data
 def raise_for_status(self):return None
class HTTP:
 def __init__(self):self.posts=[];self.gets=[]
 def post(self,url,**kwargs):self.posts.append((url,kwargs));return Response({"access_token":"fresh","refresh_token":"refresh","expires_in":3600,"id":"google-id"})
 def patch(self,url,**kwargs):return self.post(url,**kwargs)
 def get(self,url,**kwargs):self.gets.append((url,kwargs));return Response({"messages":[],"files":[{"id":"1","name":"cv.docx","appProperties":{"tumeloJobAgent":"true"}}]})
def configured(monkeypatch,tmp_path):
 monkeypatch.setenv("GOOGLE_CLIENT_ID","client-id");monkeypatch.setenv("GOOGLE_REDIRECT_URI","http://127.0.0.1:8000/api/google/callback");monkeypatch.setattr(oauth,"TokenStore",lambda:TokenStore(tmp_path/"token.json"))
def test_oauth_start_pkce_and_state(monkeypatch,tmp_path):
 configured(monkeypatch,tmp_path);result=oauth.start_authorization(["drive"]);assert "code_challenge=" in result["authorization_url"]
 with connect() as db:assert db.execute("SELECT 1 FROM oauth_state WHERE state=?",(result["state"],)).fetchone()
def test_oauth_prefers_stable_vercel_production_url(monkeypatch,tmp_path):
 configured(monkeypatch,tmp_path);monkeypatch.setenv("VERCEL","1");monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL","tumelo-job-agent.vercel.app");result=oauth.start_authorization(["drive"]);assert "redirect_uri=https%3A%2F%2Ftumelo-job-agent.vercel.app%2Fapi%2Fgoogle%2Fcallback" in result["authorization_url"]
 with connect() as db:assert db.execute("SELECT redirect_uri FROM oauth_state WHERE state=?",(result["state"],)).fetchone()[0]=="https://tumelo-job-agent.vercel.app/api/google/callback"
def test_oauth_callback_rejects_bad_state(monkeypatch,tmp_path):
 configured(monkeypatch,tmp_path)
 with pytest.raises(ValueError):oauth.complete_authorization("code","bad",HTTP())
def test_oauth_callback_and_refresh(monkeypatch,tmp_path):
 configured(monkeypatch,tmp_path);started=oauth.start_authorization(["gmail"]);summary=oauth.complete_authorization("code",started["state"],HTTP());assert summary["connected"]
 store=TokenStore(tmp_path/"refresh.json");store.save({"refresh_token":"r","expires_at":0});monkeypatch.setattr(oauth,"TokenStore",lambda:store);assert oauth.access_token(HTTP())=="fresh"
def test_gmail_classification_and_send_guard():
 result=gmail.classify_email("Interview invitation","We invite you for an interview");assert result["classification"]=="INTERVIEW_INVITE" and result["confidence"]>.8
 with pytest.raises(PermissionError):gmail.send_message("a@example.test","Role","Factual body",explicit=False)
def test_gmail_search_and_draft(monkeypatch,tmp_path):
 store=TokenStore(tmp_path/"g.json");store.save({"access_token":"x","expires_at":time.time()+1000});monkeypatch.setattr(gmail,"access_token",lambda http:"x");http=HTTP();assert gmail.search_messages(http=http)==[];assert gmail.create_draft("a@example.test","Role","Body",http=http)["id"]=="google-id"
def test_drive_listing_upload_and_conflict(monkeypatch,tmp_path):
 monkeypatch.setattr(drive,"access_token",lambda http:"x");http=HTTP();assert drive.list_app_files(http)[0]["id"]=="1";p=tmp_path/"cv.docx";p.write_bytes(b"PK factual");assert drive.upload_file(p,http=http)["id"]=="google-id";assert drive.sync_decision("new","old","remote-new","remote-old")=="SYNC_CONFLICT"
def test_calendar_confirmation_and_duplicate(monkeypatch):
 monkeypatch.setattr(calendar,"access_token",lambda http:"x");event={"summary":"Interview","start":{"dateTime":"2030-01-01T10:00:00+02:00"},"end":{"dateTime":"2030-01-01T11:00:00+02:00"},"source_thread_id":"thread"}
 with pytest.raises(PermissionError):calendar.create_event(event,False,HTTP())
 first=calendar.create_event(event,True,HTTP());second=calendar.create_event(event,True,HTTP());assert not first["duplicate"] and second["duplicate"]
def test_disconnect(monkeypatch,tmp_path):
 store=TokenStore(tmp_path/"token.json");store.save({"access_token":"x"});monkeypatch.setattr(oauth,"TokenStore",lambda:store);oauth.disconnect();assert not store.summary()["connected"]
