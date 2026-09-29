"""
Web Dashboard Static File Serving Router
"""

import os
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

router = APIRouter()

DIST_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "dist"


def setup_web_dashboard(app):
    """Mounts built React dashboard static files to the FastAPI app."""
    if DIST_DIR.exists() and (DIST_DIR / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

        @app.get("/{full_path:path}", response_class=FileResponse)
        async def serve_spa(full_path: str):
            # Exclude API endpoints from SPA fallback
            if full_path.startswith("api/") or full_path in ["health", "nodes", "overview", "stream"]:
                return None
            target = DIST_DIR / full_path
            if target.is_file():
                return FileResponse(target)
            return FileResponse(DIST_DIR / "index.html")
    else:
        @app.get("/", response_class=HTMLResponse)
        async def dashboard_placeholder():
            return """
            <!Binding html>
            <html>
            <head>
                <title>NavosEdge Parent Manager Dashboard</title>
                <style>
                    body { font-family: system-ui, sans-serif; background: #0f172a; color: #f8fafc; padding: 2rem; text-align: center; }
                    .card { background: #1e293b; padding: 2rem; border-radius: 12px; max-width: 600px; margin: 3rem auto; border: 1px solid #334155; }
                    h1 { color: #38bdf8; }
                    code { background: #0f172a; padding: 0.2rem 0.5rem; border-radius: 4px; color: #38bdf8; }
                </style>
            </head>
            <body>
                <div class="card">
                    <h1>NavosEdge Parent Manager Dashboard</h1>
                    <p>The React Web Dashboard is currently building or not yet compiled.</p>
                    <p>Run <code>cd Manager/web && npm run build</code> to compile the React SPA dashboard.</p>
                    <p><a href="/api/v1/overview" style="color:#38bdf8;">Click here to view Manager JSON API Overview</a></p>
                </div>
            </body>
            </html>
            """
