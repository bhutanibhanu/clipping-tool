"""FastAPI application (Phase 0: health + a placeholder index).

Bind to 127.0.0.1 only — this is a single-operator local tool with no auth.
The review/approve routes and background-job endpoints arrive in Phase 4.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from clipper import __version__

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

app = FastAPI(title="clipper", version=__version__)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return _TEMPLATES.TemplateResponse(request, "index.html", {"version": __version__})
