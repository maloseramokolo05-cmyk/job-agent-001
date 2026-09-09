from __future__ import annotations
import hashlib,json,mimetypes
from pathlib import Path
import requests
from .oauth import access_token
BASE="https://www.googleapis.com/drive/v3"; UPLOAD="https://www.googleapis.com/upload/drive/v3"
def file_hash(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def list_app_files(http=requests):
 token=access_token(http); query="trashed=false and appProperties has { key='tumeloJobAgent' and value='true' }"; r=http.get(f"{BASE}/files",headers={"Authorization":f"Bearer {token}"},params={"q":query,"spaces":"drive","fields":"files(id,name,mimeType,modifiedTime,appProperties)","pageSize":100},timeout=30); r.raise_for_status(); return r.json().get("files",[])
def upload_file(path,folder_id=None,existing_id=None,http=requests):
 path=Path(path); token=access_token(http); metadata={"name":path.name,"appProperties":{"tumeloJobAgent":"true","sha256":file_hash(path)}}
 if folder_id:metadata["parents"]=[folder_id]
 boundary="tumelo-job-agent-boundary"; mime=mimetypes.guess_type(path.name)[0] or "application/octet-stream"; body=(f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(metadata)}\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n").encode()+path.read_bytes()+f"\r\n--{boundary}--".encode(); url=f"{UPLOAD}/files/{existing_id}" if existing_id else f"{UPLOAD}/files"; method=http.patch if existing_id else http.post; r=method(url,headers={"Authorization":f"Bearer {token}","Content-Type":f"multipart/related; boundary={boundary}"},params={"uploadType":"multipart","fields":"id,name,modifiedTime,appProperties"},data=body,timeout=60); r.raise_for_status(); return r.json()
def sync_decision(local_hash,recorded_local_hash,remote_hash,recorded_remote_hash):
 local_changed=bool(recorded_local_hash and local_hash!=recorded_local_hash); remote_changed=bool(recorded_remote_hash and remote_hash!=recorded_remote_hash)
 if local_changed and remote_changed:return "SYNC_CONFLICT"
 if local_changed:return "UPLOAD_LOCAL"
 if remote_changed:return "DOWNLOAD_REMOTE"
 return "IN_SYNC"
