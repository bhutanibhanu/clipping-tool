from __future__ import annotations

from fastapi.testclient import TestClient

from clipper import __version__
from clipper.web.app import app

client = TestClient(app)


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": __version__}


def test_index_renders() -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert __version__ in r.text
