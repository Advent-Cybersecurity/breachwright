import os
import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.jobs.models import Job
from app.engagements.models import Engagement, EvidenceNote, ScanUpload
from app.jobs.runner import (
    start_job, stop_job, get_job_output, cleanup_job,
    get_presets, TOOL_PRESETS, read_job_artifact,
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
    notebook_note_id: Optional[str] = None
    scan_upload_id: Optional[str] = None

    model_config = {"from_attributes": True}


class NotebookFromJobInput(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    asset: Optional[str] = Field(default=None, max_length=500)
    tags: list[str] = Field(default_factory=list, max_length=20)

    model_config = {"str_strip_whitespace": True, "extra": "forbid"}

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value):
        if any(not tag or len(tag) > 50 for tag in value):
            raise ValueError("Tags must contain between 1 and 50 characters")
        if len({tag.casefold() for tag in value}) != len(value):
            raise ValueError("Tags must be unique")
        return value


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
    job_ids = [job.id for job in jobs]
    notebook_by_job = dict((await db.execute(
        select(EvidenceNote.source_id, EvidenceNote.id).where(
            EvidenceNote.source_type == "tool_runner_job",
            EvidenceNote.source_id.in_(job_ids),
        )
    )).all()) if job_ids else {}
    scan_by_job = dict((await db.execute(
        select(ScanUpload.source_job_id, ScanUpload.id).where(
            ScanUpload.source_job_id.in_(job_ids)
        )
    )).all()) if job_ids else {}

    responses = []
    for job in jobs:
        resp = _job_to_response(job, notebook_by_job.get(job.id), scan_by_job.get(job.id))
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
            recovered = False
            artifact = read_job_artifact(output_dir)
            if artifact:
                filename, content = artifact
                job.status = "complete"
                job.output = content
                job.completed_at = job.completed_at or datetime.now(timezone.utc)
                job.exit_code = 0
                recovered = True
                logger.info("Recovered output for job %s from %s", job.id, filename)
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

    notebook_note_id = (await db.execute(
        select(EvidenceNote.id).where(
            EvidenceNote.source_type == "tool_runner_job",
            EvidenceNote.source_id == job.id,
        )
    )).scalar_one_or_none()
    scan_upload_id = (await db.execute(
        select(ScanUpload.id).where(ScanUpload.source_job_id == job.id)
    )).scalar_one_or_none()
    resp = _job_to_response(job, notebook_note_id, scan_upload_id)

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
            resp.output = job.output
            resp.status = job.status
            resp.exit_code = job.exit_code
            resp.completed_at = (
                job.completed_at.isoformat() if job.completed_at else None
            )

    return resp


@router.post("/{job_id}/notebook", status_code=201)
async def save_job_to_notebook(
    job_id: str,
    body: NotebookFromJobInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    live = get_job_output(job.id)
    status = live.get("status") if live else job.status
    if status not in {"complete", "failed", "stopped", "interrupted"}:
        raise HTTPException(status_code=409, detail="Wait for the Tool Runner job to finish before saving its output")
    existing = (await db.execute(
        select(EvidenceNote.id).where(
            EvidenceNote.engagement_id == job.engagement_id,
            EvidenceNote.source_type == "tool_runner_job",
            EvidenceNote.source_id == job.id,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="This Tool Runner job is already saved in the Evidence Notebook")

    output = str((live or {}).get("output") or job.output or "No output was captured.")
    header = (
        f"Tool: {job.tool}\n"
        f"Status: {status}\n"
        f"Exit code: {(live or {}).get('exit_code', job.exit_code)}\n"
        f"Command: {job.command}\n\n"
        "Output:\n"
    )
    available = max(0, 200000 - len(header))
    truncated = len(output) > available
    if truncated:
        marker = "\n[Output truncated to the Evidence Notebook note limit.]"
        output = output[:max(0, available - len(marker))] + marker
    note = EvidenceNote(
        engagement_id=job.engagement_id,
        title=body.title or f"{job.tool.upper()} Tool Runner output",
        body=(header + output)[:200000],
        asset=body.asset,
        tags=body.tags or [job.tool, "tool-runner"],
        source_type="tool_runner_job",
        source_id=job.id,
        created_by=current_user.id,
    )
    db.add(note)
    await db.flush()
    await db.refresh(note)
    return {
        "id": note.id,
        "title": note.title,
        "body": note.body,
        "asset": note.asset,
        "tags": note.tags,
        "source_type": note.source_type,
        "source_id": note.source_id,
        "attachments": [],
        "finding_id": None,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
    }


@router.post("/{job_id}/scan", status_code=201)
async def save_job_to_scans(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.tool not in {"nmap", "nuclei"}:
        raise HTTPException(
            status_code=422,
            detail="Only structured Nmap and Nuclei Tool Runner results can be added directly to Scans",
        )
    live = get_job_output(job.id)
    status = live.get("status") if live else job.status
    if status != "complete":
        raise HTTPException(status_code=409, detail="Wait for the Tool Runner job to complete before adding it to Scans")
    existing = (await db.execute(
        select(ScanUpload).where(ScanUpload.source_job_id == job.id)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="This Tool Runner job is already present in Scans")
    output_dir = os.path.join(settings.data_dir, "jobs", job.id)
    artifact = read_job_artifact(output_dir)
    if not artifact:
        raise HTTPException(
            status_code=422,
            detail="No structured output artifact was captured for this Tool Runner job",
        )
    artifact_name, artifact_text = artifact
    extension = ".jsonl" if job.tool == "nuclei" else ".txt"
    display_name = f"{job.tool}-job-{job.id[:8]}{extension}"
    upload_dir = os.path.join(settings.data_dir, "uploads", job.engagement_id)
    os.makedirs(upload_dir, exist_ok=True)
    stored_path = os.path.join(upload_dir, f"{uuid.uuid4().hex}{extension}")
    with open(stored_path, "wb") as stored:
        stored.write(artifact_text.encode("utf-8"))
    scan = ScanUpload(
        engagement_id=job.engagement_id,
        filename=display_name,
        file_path=stored_path,
        scan_type=job.tool,
        source_job_id=job.id,
        uploaded_by=current_user.id,
    )
    db.add(scan)
    await db.flush()
    return {
        "id": scan.id,
        "filename": scan.filename,
        "scan_type": scan.scan_type,
        "source_job_id": scan.source_job_id,
        "artifact_name": artifact_name,
    }


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


def _job_to_response(
    job: Job,
    notebook_note_id: str | None = None,
    scan_upload_id: str | None = None,
) -> JobResponse:
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
        notebook_note_id=notebook_note_id,
        scan_upload_id=scan_upload_id,
    )
