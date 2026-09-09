from __future__ import annotations
import json,os
from pathlib import Path
from backend.config import private_path
class TokenStore:
 def __init__(self,path=None): self.path=Path(path or private_path("data","tokens","google_token.json"))
 def save(self,value):
  self.path.parent.mkdir(parents=True,exist_ok=True); self.path.write_text(json.dumps(value),encoding="utf-8")
  try: self.path.chmod(0o600)
  except OSError: pass
 def load(self):
  if not self.path.exists(): return None
  return json.loads(self.path.read_text(encoding="utf-8"))
 def clear(self):
  if self.path.exists(): self.path.unlink()
 def summary(self):
  token=self.load() or {}; return {"connected":bool(token.get("access_token") or token.get("refresh_token")),"scopes":token.get("scope","").split(),"expires_at":token.get("expires_at")}
