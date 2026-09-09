from __future__ import annotations
import base64,hashlib,hmac,ipaddress,os,secrets,socket,time
from collections import defaultdict,deque
from datetime import datetime,timedelta,timezone
from urllib.parse import urlparse
from fastapi import HTTPException,Request
from backend.database import connect,now
PBKDF2_ROUNDS=600_000; COOKIE="tja_session"; _attempts=defaultdict(deque)
def _session_secret():return os.getenv("SESSION_SECRET") or os.getenv("ADMIN_PASSWORD","")
def _signed(raw):return raw+"."+hmac.new(_session_secret().encode(),raw.encode(),hashlib.sha256).hexdigest()
def _unsigned(value):
 try:raw,signature=value.rsplit(".",1)
 except ValueError:return None
 expected=hmac.new(_session_secret().encode(),raw.encode(),hashlib.sha256).hexdigest();return raw if hmac.compare_digest(signature,expected) else None
def hash_password(password,salt=None):
 salt=salt or secrets.token_bytes(16);digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,PBKDF2_ROUNDS);return f"pbkdf2_sha256${PBKDF2_ROUNDS}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"
def verify_password(password,encoded):
 try:_,rounds,salt,digest=encoded.split("$");actual=hashlib.pbkdf2_hmac("sha256",password.encode(),base64.urlsafe_b64decode(salt),int(rounds));return hmac.compare_digest(actual,base64.urlsafe_b64decode(digest))
 except (ValueError,TypeError):return False
def bootstrap_owner():
 with connect() as db:
  if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():return
  password=os.getenv("ADMIN_PASSWORD")
  if not password or len(password)<12:raise RuntimeError("ADMIN_PASSWORD must be set to at least 12 characters on first startup")
  db.execute("INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)",(os.getenv("ADMIN_USERNAME","owner"),hash_password(password),now()))
def check_rate_limit(key,limit=5,window=300):
 current=time.time();q=_attempts[key]
 while q and q[0]<current-window:q.popleft()
 if len(q)>=limit:raise HTTPException(429,"Too many login attempts; try again later")
 q.append(current)
def login(username,password,client):
 check_rate_limit(client)
 with connect() as db:
  user=db.execute("SELECT * FROM users WHERE username=?",(username,)).fetchone()
  if not user or not verify_password(password,user[2]):raise HTTPException(401,"Invalid credentials")
  token=secrets.token_urlsafe(48);csrf=secrets.token_urlsafe(32);expires=datetime.now(timezone.utc)+timedelta(hours=int(os.getenv("SESSION_HOURS","12")));db.execute("INSERT INTO sessions(token_hash,user_id,csrf_token,expires_at,created_at) VALUES(?,?,?,?,?)",(hashlib.sha256(token.encode()).hexdigest(),user[0],csrf,expires.isoformat(),now()));return _signed(token),csrf,expires
def session(request):
 token=_unsigned(request.cookies.get(COOKIE, ""))
 if not token:return None
 with connect() as db:return db.execute("SELECT * FROM sessions WHERE token_hash=? AND expires_at>?",(hashlib.sha256(token.encode()).hexdigest(),now())).fetchone()
def logout(token):
 token=_unsigned(token or "")
 if token:
  with connect() as db:db.execute("DELETE FROM sessions WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),))
def validate_csrf(request,sess):
 if request.method not in {"GET","HEAD","OPTIONS"} and not hmac.compare_digest(request.headers.get("X-CSRF-Token",""),sess[3]):raise HTTPException(403,"CSRF validation failed")
def validate_public_url(url):
 parsed=urlparse(url)
 if parsed.scheme not in {"http","https"} or not parsed.hostname or parsed.username or parsed.password:raise ValueError("Only public HTTP(S) URLs are allowed")
 if parsed.hostname.lower() in {"localhost","localhost.localdomain"}:raise ValueError("Local URLs are not allowed")
 try:addresses=socket.getaddrinfo(parsed.hostname,parsed.port or (443 if parsed.scheme=="https" else 80),type=socket.SOCK_STREAM)
 except socket.gaierror as exc:raise ValueError("Source hostname cannot be resolved") from exc
 for address in addresses:
  ip=ipaddress.ip_address(address[4][0])
  if not ip.is_global:raise ValueError("Private, loopback, link-local, and metadata addresses are blocked")
 return url
