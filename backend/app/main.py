import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
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

    # Run Alembic migrations
    try:
        import threading
        from alembic.config import Config as AlembicConfig
        from alembic import command

        def _run_migrations():
            alembic_cfg = AlembicConfig(
                os.path.join(BASE_DIR, "backend", "alembic.ini")
            )
            alembic_cfg.set_main_option("sqlalchemy.url", settings.resolved_database_url)
            alembic_cfg.set_main_option(
                "script_location",
                os.path.join(BASE_DIR, "backend", "alembic")
            )
            command.upgrade(alembic_cfg, "head")

        # Run in thread to avoid nested asyncio.run conflict
        t = threading.Thread(target=_run_migrations)
        t.start()
        t.join(timeout=30)
        logger.info("Database migrations complete")
    except Exception as e:
        logger.error("Migration error: %s", e)

    logger.info("All Breachwright features are available in this open-source build")

    yield
    # Flush running job output to DB before shutdown
    try:
        from app.jobs.runner import flush_all_to_db_sync
        flush_all_to_db_sync()
    except Exception as e:
        logger.error("Job flush on shutdown failed: %s", e)
    logger.info("Breachwright shutting down")


APP_VERSION = "2.0.0"

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

# API Routers
from app.auth.router import router as auth_router
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

app.include_router(auth_router)
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
                    "update_available": latest and latest != APP_VERSION,
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
        # Don't intercept /api routes
        if full_path.startswith("api"):
            return
        file_path = os.path.join(FRONTEND_DIR, full_path)
        if os.path.isfile(file_path):
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
