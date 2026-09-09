from __future__ import annotations
import base64,hashlib,json,os,secrets,time
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlencode
import requests
from backend.config import private_path
from backend.database import connect,now
from .models import FEATURE_SCOPES
from .token_store import TokenStore
AUTH_URL="https://accounts.google.com/o/oauth2/v2/auth"; TOKEN_URL="https://oauth2.googleapis.com/token"
def client_config():
 cid=os.getenv("GOOGLE_CLIENT_ID",""); secret=os.getenv("GOOGLE_CLIENT_SECRET","")
 path=Path(os.getenv("GOOGLE_CREDENTIALS_FILE",private_path("data","secrets","credentials.json")))
 if path.exists():
  raw=json.loads(path.read_text(encoding="utf-8")); item=raw.get("web") or raw.get("installed") or {}; cid=cid or item.get("client_id",""); secret=secret or item.get("client_secret","")
 return cid,secret
def scopes_for(features): return sorted({scope for feature in features for scope in FEATURE_SCOPES.get(feature,[])})
def start_authorization(features,redirect_uri=None):
 cid,_=client_config()
 if not cid: raise ValueError("Google OAuth client is not configured")
 redirect_uri=redirect_uri or os.getenv("GOOGLE_REDIRECT_URI","http://127.0.0.1:8000/api/google/callback")
 state=secrets.token_urlsafe(32); verifier=secrets.token_urlsafe(64); challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode(); scopes=scopes_for(features)
 created=datetime.now(timezone.utc); expires=created+timedelta(minutes=10)
 with connect() as db: db.execute("INSERT INTO oauth_state VALUES(?,?,?,?,?,?)",(state,verifier,redirect_uri,json.dumps(scopes),created.isoformat(),expires.isoformat()))
 query=urlencode({"client_id":cid,"redirect_uri":redirect_uri,"response_type":"code","scope":" ".join(scopes),"access_type":"offline","include_granted_scopes":"true","prompt":"consent","state":state,"code_challenge":challenge,"code_challenge_method":"S256"})
 return {"authorization_url":f"{AUTH_URL}?{query}","state":state}
def complete_authorization(code,state,http=requests):
 with connect() as db:
  saved=db.execute("SELECT * FROM oauth_state WHERE state=?",(state,)).fetchone()
  if not saved: raise ValueError("Invalid or already-used OAuth state")
  if datetime.fromisoformat(saved[5])<datetime.now(timezone.utc): db.execute("DELETE FROM oauth_state WHERE state=?",(state,)); raise ValueError("OAuth state expired; reconnect")
  db.execute("DELETE FROM oauth_state WHERE state=?",(state,))
 cid,secret=client_config(); payload={"client_id":cid,"code":code,"code_verifier":saved[1],"grant_type":"authorization_code","redirect_uri":saved[2]}
 if secret: payload["client_secret"]=secret
 response=http.post(TOKEN_URL,data=payload,timeout=30); response.raise_for_status(); token=response.json(); token["expires_at"]=int(time.time())+int(token.get("expires_in",3600)); TokenStore().save(token); return TokenStore().summary()
def access_token(http=requests):
 store=TokenStore(); token=store.load()
 if not token: raise PermissionError("Google account is not connected")
 if token.get("access_token") and int(token.get("expires_at",0))>int(time.time())+60:return token["access_token"]
 cid,secret=client_config(); payload={"client_id":cid,"refresh_token":token.get("refresh_token"),"grant_type":"refresh_token"}
 if secret:payload["client_secret"]=secret
 try: response=http.post(TOKEN_URL,data=payload,timeout=30); response.raise_for_status()
 except Exception as exc: raise PermissionError("Google authorization expired; reconnect") from exc
 refreshed=response.json(); token.update(refreshed); token["expires_at"]=int(time.time())+int(refreshed.get("expires_in",3600)); store.save(token); return token["access_token"]
def disconnect(): TokenStore().clear()
