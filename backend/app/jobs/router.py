import os
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.jobs.models import Job
from app.engagements.models import Engagement
from app.jobs.runner import (
    start_job, stop_job, get_job_output, cleanup_job,
    get_presets, TOOL_PRESETS,
)
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobCreate(BaseModel):
    engagement_id: str = Field(min_length=1, max_length=36)
    tool: str = Field(min_length=1, max_length=50)
    command: str = Field(min_length=1, max_length=20000)


class JobResponse(BaseModel):
    id: str
    engagement_id: str
    tool: str
    command: str
    status: str
    output: Optional[str] = None
    exit_code: Optional[int] = None
    pid: Optional[int] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


@router.get("/presets")
async def list_presets(current_user: User = Depends(get_current_user)):
    """List available tool presets and check which tools are installed."""
    return get_presets()


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    body: JobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    engagement_result = await db.execute(
        select(Engagement.id).where(Engagement.id == body.engagement_id)
    )
    if not engagement_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Engagement not found")

    # Validate command is not empty
    if not body.command.strip():
        raise HTTPException(status_code=400, detail="Command cannot be empty")

    # Basic safety: block obviously dangerous commands
    dangerous = ["rm -rf /", "mkfs", "dd if=", "> /dev/sd", ":(){ :|:& };:"]
    cmd_lower = body.command.lower()
    for d in dangerous:
        if d in cmd_lower:
            raise HTTPException(status_code=400, detail="Command blocked for safety")

    # Create job record
    job = Job(
        engagement_id=body.engagement_id,
        tool=body.tool,
        command=body.command,
        status="running",
        created_by=current_user.id,
        started_at=datetime.now(timezone.utc),
    )
    db.add(job)
    await db.flush()

    # Output directory for this job
    output_dir = os.path.join(settings.data_dir, "jobs", job.id)

    # Start the subprocess
    pid = start_job(job.id, body.command, body.tool, output_dir)
    if pid is None:
        job.status = "failed"
        job.output = "Failed to start process"
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()
        raise HTTPException(status_code=500, detail="Failed to start tool process")

    job.pid = pid
    await db.flush()

    logger.info("Started job %s (PID %d): %s", job.id, pid, body.command)

    return _job_to_response(job)


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    engagement_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Job)
        .where(Job.engagement_id == engagement_id)
        .order_by(Job.created_at.desc())
    )
    jobs = result.scalars().all()

    responses = []
    for job in jobs:
        resp = _job_to_response(job)
        # Overlay live output for running jobs
        live = get_job_output(job.id)
        if live:
            resp.output = live["output"]
            resp.status = live["status"]
            resp.exit_code = live.get("exit_code")
        elif job.status == "running":
            # Process not in memory — app restarted while it was running
            # Check if the output file exists and has content (scan may have finished)
            import os as _os
            output_dir = _os.path.join(settings.data_dir, "jobs", job.id)
            output_file = _os.path.join(output_dir, "output.txt")
            recovered = False
            if _os.path.isdir(output_dir):
                # Look for any output files the tool wrote
                for fname in _os.listdir(output_dir):
                    fpath = _os.path.join(output_dir, fname)
                    if _os.path.isfile(fpath) and _os.path.getsize(fpath) > 0:
                        try:
                            with open(fpath, "r", errors="replace") as _f:
                                content = _f.read()
                            if content.strip():
                                job.status = "complete"
                                job.output = content[:500000]  # cap at 500KB
                                job.completed_at = job.completed_at or datetime.now(timezone.utc)
                                job.exit_code = 0
                                recovered = True
                                logger.info("Recovered output for job %s from %s", job.id, fname)
                                break
                        except Exception:
                            pass
            if not recovered:
                job.status = "interrupted"
                job.output = (job.output or "") + "\n[App closed while scan was running]"
                job.completed_at = datetime.now(timezone.utc)
            await db.flush()
            resp.status = job.status
            resp.output = job.output
        responses.append(resp)

    return responses


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    resp = _job_to_response(job)

    # Overlay live output
    live = get_job_output(job.id)
    if live:
        resp.output = live["output"]
        resp.status = live["status"]
        resp.exit_code = live.get("exit_code")

    # If job finished in memory but not yet flushed to DB, flush it
    if live and live["status"] in ("complete", "failed", "stopped"):
        final = cleanup_job(job.id)
        if final:
            job.output = final["output"]
            job.status = final.get("status", "complete")
            job.exit_code = final.get("exit_code")
            job.completed_at = final.get("completed_at")
            await db.flush()

    return resp


@router.post("/{job_id}/stop")
async def stop_running_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    success = stop_job(job_id)
    if not success:
        # Process might already be dead - just mark it
        if job.status == "running":
            job.status = "stopped"
            job.completed_at = datetime.now(timezone.utc)
            await db.flush()
            return {"status": "stopped"}
        raise HTTPException(status_code=400, detail="Job is not running")

    # Flush final state
    final = cleanup_job(job_id)
    if final:
        job.output = final["output"]
        job.status = "stopped"
        job.exit_code = -1
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()

    return {"status": "stopped"}


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Stop if running
    stop_job(job_id)
    cleanup_job(job_id)

    # Clean up output directory
    output_dir = os.path.join(settings.data_dir, "jobs", job_id)
    if os.path.isdir(output_dir):
        import shutil
        shutil.rmtree(output_dir, ignore_errors=True)

    await db.delete(job)


def _job_to_response(job: Job) -> JobResponse:
    return JobResponse(
        id=job.id,
        engagement_id=job.engagement_id,
        tool=job.tool,
        command=job.command,
        status=job.status,
        output=job.output,
        exit_code=job.exit_code,
        pid=job.pid,
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        created_at=job.created_at.isoformat() if job.created_at else None,
    )
