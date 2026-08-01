import os
import logging
import re
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.jobs.models import Job
from app.engagements.models import Engagement, EvidenceNote, ScanUpload
from app.jobs.runner import (
    start_job, stop_job, get_job_output, cleanup_job,
    build_command_arguments, get_presets, TOOL_PRESETS, read_job_artifact,
)
from app.config import settings
from app.safety import app_data_directory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobCreate(BaseModel):
    engagement_id: str = Field(min_length=1, max_length=36)
    tool: str = Field(min_length=1, max_length=50)
    execution_mode: Literal["preset", "custom"] = "custom"
    command: Optional[str] = Field(default=None, min_length=1, max_length=20000)
    preset: Optional[str] = Field(default=None, min_length=1, max_length=50)
    target: Optional[str] = Field(default=None, min_length=1, max_length=2048)
    ports: Optional[str] = Field(default=None, max_length=1000)
    timing: Optional[str] = Field(default=None, max_length=2)

    model_config = {"str_strip_whitespace": True, "extra": "forbid"}


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


SAFE_PRESET_TARGET = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:/?&=#@+,\-\[\]]{0,2047}$"
)
SAFE_NMAP_PORTS = re.compile(r"^[0-9][0-9,\-]{0,999}$")
SAFE_NMAP_TIMING = re.compile(r"^T[1-5]$")


def _build_job_command(body: JobCreate) -> str:
    if body.execution_mode == "custom":
        command = (body.command or "").strip()
        if not command:
            raise HTTPException(status_code=400, detail="Custom command cannot be empty")
        dangerous = ["rm -rf /", "mkfs", "dd if=", "> /dev/sd", ":(){ :|:& };:"]
        if any(marker in command.lower() for marker in dangerous):
            raise HTTPException(status_code=400, detail="Command blocked for safety")
        return command

    presets = TOOL_PRESETS.get(body.tool)
    preset = presets.get(body.preset or "") if presets else None
    if not preset:
        raise HTTPException(status_code=400, detail="Unknown Tool Runner preset")

    target = (body.target or "").strip()
    if not SAFE_PRESET_TARGET.fullmatch(target):
        raise HTTPException(
            status_code=422,
            detail=(
                "Preset targets must be one hostname, IP address, CIDR, or URL "
                "without spaces or shell-control characters"
            ),
        )

    command = preset["cmd"].replace("{target}", f'"{target}"')
    command = command.replace(
        "{output_file}",
        "output.jsonl" if body.tool == "nuclei" else "output.txt",
    )
    command = command.replace("{output_dir}", ".")
    command = command.replace("{input_file}", "input.txt")

    if body.tool == "nmap":
        ports = (body.ports or "").strip()
        if ports:
            if not SAFE_NMAP_PORTS.fullmatch(ports):
                raise HTTPException(
                    status_code=422,
                    detail="Nmap ports may contain only digits, commas, and hyphens",
                )
            command = re.sub(r"--top-ports \d+", f"-p {ports}", command)
            command = command.replace("-p-", f"-p {ports}")
        timing = (body.timing or "T3").strip()
        if not SAFE_NMAP_TIMING.fullmatch(timing):
            raise HTTPException(status_code=422, detail="Nmap timing must be T1 through T5")
        command = re.sub(r"-T\d", f"-{timing}", command)

    return command


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

    command = _build_job_command(body)

    # Create job record
    job = Job(
        engagement_id=body.engagement_id,
        tool=body.tool,
        command=command,
        status="running",
        created_by=current_user.id,
        started_at=datetime.now(timezone.utc),
    )
    db.add(job)
    await db.flush()

    # Output directory for this job
    output_dir = app_data_directory(settings.data_dir, "jobs", job.id)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        arguments = build_command_arguments(body.tool, command)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Start the subprocess without a command shell.
    pid = start_job(job.id, arguments, body.tool, str(output_dir))
    if pid is None:
        job.status = "failed"
        job.output = "Failed to start process"
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()
        raise HTTPException(status_code=500, detail="Failed to start tool process")

    job.pid = pid
    await db.flush()

    logger.info("Started Tool Runner job (PID %d)", pid)

    return _job_to_response(job)


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    engagement_id: str = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Job)
        .where(Job.engagement_id == engagement_id)
        .order_by(Job.created_at.desc(), Job.started_at.desc(), Job.id.desc())
        .limit(limit)
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
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This Tool Runner job is already saved in the Evidence Notebook",
        ) from exc
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
    output_dir = app_data_directory(settings.data_dir, "jobs", job.id)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact = read_job_artifact(str(output_dir))
    if not artifact:
        raise HTTPException(
            status_code=422,
            detail="No structured output artifact was captured for this Tool Runner job",
        )
    artifact_name, artifact_text = artifact
    extension = ".jsonl" if job.tool == "nuclei" else ".txt"
    display_name = f"{job.tool}-job-{job.id[:8]}{extension}"
    upload_dir = app_data_directory(
        settings.data_dir,
        "uploads",
        job.engagement_id,
    )
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_path = upload_dir / f"{uuid.uuid4().hex}{extension}"
    with stored_path.open("wb") as stored:
        stored.write(artifact_text.encode("utf-8"))
    scan = ScanUpload(
        engagement_id=job.engagement_id,
        filename=display_name,
        file_path=str(stored_path),
        scan_type=job.tool,
        source_job_id=job.id,
        uploaded_by=current_user.id,
    )
    db.add(scan)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        try:
            os.remove(stored_path)
        except OSError:
            logger.warning("Could not remove failed Tool Runner scan copy")
        raise HTTPException(
            status_code=409,
            detail="This Tool Runner job is already present in Scans",
        ) from exc
    except Exception:
        try:
            os.remove(stored_path)
        except OSError:
            logger.warning("Could not remove failed Tool Runner scan copy")
        raise
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

    success = stop_job(job.id)
    if not success:
        # Process might already be dead - just mark it
        if job.status == "running":
            job.status = "stopped"
            job.completed_at = datetime.now(timezone.utc)
            await db.flush()
            return {"status": "stopped"}
        raise HTTPException(status_code=400, detail="Job is not running")

    # Flush final state
    final = cleanup_job(job.id)
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
    stop_job(job.id)
    cleanup_job(job.id)

    # Clean up output directory before removing the record so a failed cleanup
    # remains visible and can be retried by the operator.
    output_dir = app_data_directory(settings.data_dir, "jobs", job.id)
    if output_dir.is_dir():
        import shutil
        try:
            shutil.rmtree(output_dir)
        except OSError as exc:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Tool Runner output could not be removed. Review file "
                    "permissions and retry."
                ),
            ) from exc

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
