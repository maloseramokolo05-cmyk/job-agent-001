from __future__ import annotations
from urllib.parse import urljoin
import requests
from backend.security import validate_public_url
HEADERS={"User-Agent":"TumeloJobAgent/3.0 (+private career workspace)"}
def get(url,**kwargs):
 current=validate_public_url(url);timeout=kwargs.pop("timeout",20);headers=kwargs.pop("headers",HEADERS)
 for _ in range(5):
  response=requests.get(current,timeout=timeout,headers=headers,allow_redirects=False,**kwargs)
  if not response.is_redirect:response.raise_for_status();return response
  current=validate_public_url(urljoin(current,response.headers.get("location","")))
 raise ValueError("Source exceeded the redirect limit")
