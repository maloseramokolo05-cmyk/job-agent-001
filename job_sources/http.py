from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import requests

MAX_RESPONSE = 5_000_000


def safe_get(url: str, *, timeout: int = 15) -> requests.Response:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public HTTP(S) source URLs are permitted")
    for answer in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM):
        address = ipaddress.ip_address(answer[4][0])
        if not address.is_global:
            raise ValueError("Private and local network source URLs are prohibited")
    response = requests.get(
        url,
        timeout=(5, timeout),
        allow_redirects=False,
        headers={"User-Agent": "TumeloJobAgent/3.0 (+private job search)"},
        stream=True,
    )
    if response.is_redirect:
        raise ValueError("Source redirects are not followed automatically")
    response.raise_for_status()
    content = bytearray()
    for chunk in response.iter_content(64 * 1024):
        content.extend(chunk)
        if len(content) > MAX_RESPONSE:
            raise ValueError("Source response exceeded 5 MB")
    response._content = bytes(content)
    response._content_consumed = True
    return response
