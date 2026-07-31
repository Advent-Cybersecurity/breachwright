import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.auth.local_owner import ensure_local_owner
from app.db.migrations import run_migrations
from app.version import APP_VERSION, is_newer_version
import sys

def _get_base_dir():
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_DIR = _get_base_dir()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("breachwright")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: run migrations
    logger.info("Breachwright starting up")
    logger.info("Data directory: %s", settings.data_dir)
    logger.info("Database: %s", "SQLite" if "sqlite" in settings.resolved_database_url else "PostgreSQL")

    try:
        await run_migrations(BASE_DIR, settings.resolved_database_url)
        logger.info("Database migrations complete")
        owner = await ensure_local_owner()
        logger.info("Local workspace owner ready: %s", owner.id)
    except Exception:
        logger.exception("Database migration failed; startup aborted")
        raise

    logger.info("All Breachwright features are available in this open-source build")

    yield
    # Flush running job output to DB before shutdown
    try:
        from app.jobs.runner import flush_all_to_db_sync
        flush_all_to_db_sync()
    except Exception as e:
        logger.error("Job flush on shutdown failed: %s", e)
    logger.info("Breachwright shutting down")


app = FastAPI(
    title="Breachwright",
    description=(
        "Open-source penetration test management software created by "
        "Advent Cybersecurity."
    ),
    version=APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=()",
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'"
        ),
    )
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


# API Routers
from app.engagements.router import router as engagements_router
from app.findings.router import router as findings_router
from app.findings.evidence import router as evidence_router
from app.analysis.router import router as analysis_router
from app.attack_paths.router import router as attack_paths_router
from app.reports.router import router as reports_router
from app.settings_router import router as settings_router
from app.engagements.export_import import router as export_import_router
from app.ad.router import router as ad_router
from app.jobs.router import router as jobs_router
from app.assistant.router import router as assistant_router
from app.checklists.router import router as checklists_router
from app.reports.template_router import router as template_router
from app.knowledge.router import router as knowledge_router
from app.gap_detection.router import router as gap_analysis_router
from app.correlation.router import router as correlation_router
from app.narrative.router import router as narrative_router
from app.system.router import router as system_router

app.include_router(engagements_router)
app.include_router(findings_router)
app.include_router(evidence_router)
app.include_router(analysis_router)
app.include_router(attack_paths_router)
app.include_router(reports_router)
app.include_router(settings_router)
app.include_router(export_import_router)
app.include_router(ad_router)
app.include_router(jobs_router)
app.include_router(assistant_router)
app.include_router(checklists_router)
app.include_router(template_router)
app.include_router(knowledge_router)
app.include_router(gap_analysis_router)
app.include_router(correlation_router)
app.include_router(narrative_router)
app.include_router(system_router)


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "version": APP_VERSION,
        "distribution": "open_source",
    }


@app.get("/api/version-check")
async def version_check():
    """Check for updates via GitHub releases API."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                "https://api.github.com/repos/Advent-Cybersecurity/Breachwright/releases/latest",
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                latest = data.get("tag_name", "").lstrip("v")
                return {
                    "current": APP_VERSION,
                    "latest": latest,
                    "update_available": bool(
                        latest and is_newer_version(latest, APP_VERSION)
                    ),
                    "release_url": data.get("html_url", ""),
                    "release_notes": data.get("body", "")[:500],
                }
    except Exception:
        pass
    return {"current": APP_VERSION, "latest": APP_VERSION, "update_available": False}


# Serve frontend static files
# The built React app goes in frontend/dist/ relative to the project root
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend", "dist")

if os.path.isdir(FRONTEND_DIR):
    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")

    # Catch-all: serve index.html for SPA routing
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Unknown API routes must not look like successful empty responses.
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        frontend_root = os.path.realpath(FRONTEND_DIR)
        file_path = os.path.realpath(os.path.join(frontend_root, full_path))
        try:
            within_frontend = (
                os.path.commonpath([frontend_root, file_path]) == frontend_root
            )
        except ValueError:
            within_frontend = False
        if within_frontend and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
else:
    @app.get("/")
    async def no_frontend():
        return {
            "message": "Breachwright API is running. Frontend not built yet.",
            "docs": "/api/docs",
            "hint": "Run 'cd frontend && npm install && npm run build' to build the UI.",
        }
