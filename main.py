"""Vercel entrypoint for StreamCrew FastAPI application."""
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="StreamCrew", docs_url=None, redoc_url=None)

STATIC_DIR = Path(__file__).resolve().parent / "src" / "streamcrew" / "static"


@app.get("/", response_class=HTMLResponse)
def get_landing() -> HTMLResponse:
    """Serve the StreamCrew interactive landing page and system simulation."""
    landing = STATIC_DIR / "index.html"
    if landing.exists():
        return HTMLResponse(landing.read_text(encoding="utf-8"))
    return HTMLResponse("<!doctype html><title>StreamCrew</title>")


@app.get("/overlay", response_class=HTMLResponse)
def get_overlay() -> HTMLResponse:
    """Serve the StreamCrew OBS overlay."""
    overlay = STATIC_DIR / "overlay.html"
    if overlay.exists():
        return HTMLResponse(overlay.read_text(encoding="utf-8"))
    return HTMLResponse("<!doctype html><title>StreamCrew Overlay</title>")
