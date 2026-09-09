import socket

import pytest

from job_sources.http import safe_get


def test_source_rejects_non_http_urls():
    with pytest.raises(ValueError, match="HTTP"):
        safe_get("file:///etc/passwd")


def test_source_rejects_private_network(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 80))])
    with pytest.raises(ValueError, match="Private"):
        safe_get("http://internal.example/jobs")
