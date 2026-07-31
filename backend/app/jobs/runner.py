"""Job runner engine.

Manages subprocess execution in background threads with real-time
output capture. Periodically flushes output to DB so nothing is lost
on shutdown.
"""
import os
import signal
import subprocess
import threading
import logging
import shutil
from collections import deque
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_running_jobs: dict = {}
_lock = threading.Lock()
MAX_JOB_OUTPUT = 500_000
TRUNCATION_NOTICE = "[Earlier output truncated]\n"
ARTIFACT_FILENAMES = ("output.xml", "output.jsonl", "output.txt")

TOOL_PRESETS = {
    "nmap": {
        "quick": {"name": "Quick Scan", "description": "Top 100 ports, service detection", "cmd": "nmap -sV -sC --top-ports 100 -T3 -oN {output_file} {target}"},
        "full": {"name": "Full Port Scan", "description": "All 65535 ports, version + scripts", "cmd": "nmap -sV -sC -p- -T4 -oN {output_file} {target}"},
        "stealth": {"name": "Stealth Scan", "description": "SYN scan, no ping, slow timing", "cmd": "nmap -sS -Pn -T1 --top-ports 1000 -oN {output_file} {target}"},
        "vuln": {"name": "Vulnerability Scan", "description": "Top ports + vuln NSE scripts", "cmd": "nmap -sV --script=vuln --top-ports 1000 -T3 -oN {output_file} {target}"},
        "udp": {"name": "UDP Scan", "description": "Top 100 UDP ports", "cmd": "nmap -sU --top-ports 100 -T3 -oN {output_file} {target}"},
    },
    "subfinder": {
        "default": {"name": "Subdomain Enumeration", "description": "Passive subdomain discovery", "cmd": "subfinder -d {target} -silent -o {output_file}"},
    },
    "httpx": {
        "default": {"name": "HTTP Probe", "description": "Probe discovered hosts for web services", "cmd": "httpx -l {input_file} -silent -title -status-code -tech-detect -o {output_file}"},
        "from_target": {"name": "HTTP Probe (single target)", "description": "Probe a single target", "cmd": "echo {target} | httpx -silent -title -status-code -tech-detect -o {output_file}"},
    },
    "gowitness": {
        "default": {"name": "Web Screenshots", "description": "Screenshot discovered web services", "cmd": "gowitness file -f {input_file} --screenshot-path {output_dir}"},
    },
    "nikto": {
        "default": {"name": "Nikto Scan", "description": "Web server vulnerability scan", "cmd": "nikto -h {target} -o {output_file} -Format txt"},
    },
    "feroxbuster": {
        "default": {"name": "Directory Brute Force", "description": "Content discovery with common wordlist", "cmd": "feroxbuster -u {target} -w /usr/share/seclists/Discovery/Web-Content/common.txt -o {output_file} --no-state"},
    },
    "nuclei": {
        "cves": {"name": "CVE Detection", "description": "Scan for known CVEs", "cmd": "nuclei -u {target} -t cves/ -jsonl -o {output_file} -silent"},
        "misconfig": {"name": "Misconfigurations", "description": "Detect common misconfigurations", "cmd": "nuclei -u {target} -t misconfiguration/ -jsonl -o {output_file} -silent"},
        "exposures": {"name": "Exposures", "description": "Detect exposed panels, files, and data", "cmd": "nuclei -u {target} -t exposures/ -jsonl -o {output_file} -silent"},
        "all": {"name": "Full Template Scan", "description": "Run all nuclei templates (slow)", "cmd": "nuclei -u {target} -jsonl -o {output_file} -silent"},
    },
}


def get_presets():
    result = {}
    for tool, presets in TOOL_PRESETS.items():
        available = shutil.which(tool) is not None
        result[tool] = {"available": available, "path": shutil.which(tool) if available else None, "presets": presets}
    return result


def _append_job_output(state: dict, text: str) -> None:
    chunks = state["output_chunks"]
    chunks.append(text)
    state["output_length"] += len(text)

    retained_limit = MAX_JOB_OUTPUT - len(TRUNCATION_NOTICE)
    while state["output_length"] > retained_limit and chunks:
        overflow = state["output_length"] - retained_limit
        first = chunks[0]
        if len(first) <= overflow:
            chunks.popleft()
            state["output_length"] -= len(first)
        else:
            chunks[0] = first[overflow:]
            state["output_length"] -= overflow
        state["output_truncated"] = True


def _render_job_output(state: dict) -> str:
    output = "".join(state["output_chunks"])
    if state["output_truncated"]:
        return TRUNCATION_NOTICE + output
    return output


def read_job_artifact(output_dir: str) -> Optional[tuple[str, str]]:
    """Read one app-owned text artifact without following links or exceeding the job bound."""
    root = os.path.realpath(output_dir)
    for filename in ARTIFACT_FILENAMES:
        candidate = os.path.join(root, filename)
        if os.path.islink(candidate) or not os.path.isfile(candidate):
            continue
        if os.path.dirname(os.path.realpath(candidate)) != root:
            continue
        try:
            with open(candidate, "rb") as artifact:
                content = artifact.read(MAX_JOB_OUTPUT + 1)
        except OSError:
            continue
        truncated = len(content) > MAX_JOB_OUTPUT
        text = content[:MAX_JOB_OUTPUT].decode("utf-8", errors="replace")
        if truncated:
            text += "\n[Saved tool artifact truncated]"
        if text.strip():
            return filename, text
    return None


def start_job(job_id: str, command: str, tool: str, output_dir: str) -> Optional[int]:
    os.makedirs(output_dir, exist_ok=True)
    logger.info("Starting %s job %s", tool, job_id)
    try:
        process = subprocess.Popen(
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, cwd=output_dir,
            preexec_fn=os.setsid if os.name != "nt" else None,
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP
                if os.name == "nt"
                else 0
            ),
        )
    except Exception as e:
        logger.error("Failed to start job %s: %s", job_id, e)
        return None

    with _lock:
        _running_jobs[job_id] = {
            "process": process,
            "output_chunks": deque(),
            "output_length": 0,
            "output_truncated": False,
            "tool": tool,
            "command": command, "started_at": datetime.now(timezone.utc),
            "output_dir": output_dir,
        }

    thread = threading.Thread(target=_capture_output, args=(job_id, process), daemon=True)
    thread.start()
    with _lock:
        _running_jobs[job_id]["thread"] = thread
    return process.pid


def _capture_output(job_id: str, process: subprocess.Popen):
    try:
        for line in iter(process.stdout.readline, ""):
            if not line:
                break
            with _lock:
                if job_id in _running_jobs:
                    _append_job_output(_running_jobs[job_id], line)
        process.wait()
    except Exception as e:
        logger.error("Error capturing output for job %s: %s", job_id, e)
    finally:
        with _lock:
            if job_id in _running_jobs:
                state = _running_jobs[job_id]
                artifact = read_job_artifact(state["output_dir"])
                if artifact:
                    filename, artifact_text = artifact
                    current = _render_job_output(state)
                    if artifact_text.strip() not in current:
                        if current.strip():
                            _append_job_output(state, f"\n[Saved tool artifact: {filename}]\n")
                        _append_job_output(state, artifact_text)
                _running_jobs[job_id]["exit_code"] = process.returncode
                _running_jobs[job_id]["completed_at"] = datetime.now(timezone.utc)
                _running_jobs[job_id]["status"] = "complete" if process.returncode == 0 else "failed"


def get_job_output(job_id: str) -> Optional[dict]:
    with _lock:
        job = _running_jobs.get(job_id)
        if not job:
            return None
        process = job["process"]
        return {
            "output": _render_job_output(job),
            "status": job.get("status", "running" if process.poll() is None else "complete"),
            "pid": process.pid,
            "exit_code": job.get("exit_code"),
            "started_at": job["started_at"].isoformat(),
            "completed_at": job.get("completed_at").isoformat() if job.get("completed_at") else None,
        }


def _terminate_process_tree(process: subprocess.Popen, timeout: int = 5) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        result = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=timeout,
        )
        if result.returncode != 0 and process.poll() is None:
            process.terminate()
    else:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=timeout)


def stop_job(job_id: str) -> bool:
    with _lock:
        job = _running_jobs.get(job_id)
        if not job:
            return False
        process = job["process"]
    if process.poll() is not None:
        return False
    try:
        _terminate_process_tree(process)
    except Exception as e:
        logger.error("Error stopping job %s: %s", job_id, e)
        return False
    with _lock:
        if job_id in _running_jobs:
            _running_jobs[job_id]["status"] = "stopped"
            _running_jobs[job_id]["completed_at"] = datetime.now(timezone.utc)
            _running_jobs[job_id]["exit_code"] = -1
    return True


def cleanup_job(job_id: str) -> Optional[dict]:
    with _lock:
        job = _running_jobs.pop(job_id, None)
        if job is not None:
            job["output"] = _render_job_output(job)
        return job


def list_running() -> list[str]:
    with _lock:
        return [jid for jid, j in _running_jobs.items() if j["process"].poll() is None]


def flush_all_to_db_sync():
    """Flush ALL in-memory job state to the DB.

    Called on shutdown to persist output and final status for every
    job that ran during this session — whether still running or finished.
    Uses a sync DB session since this runs during shutdown (no event loop).
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.config import settings
    from app.jobs.models import Job

    with _lock:
        jobs_to_flush = {}
        for job_id, state in _running_jobs.items():
            snapshot = dict(state)
            snapshot["output"] = _render_job_output(state)
            jobs_to_flush[job_id] = snapshot

    if not jobs_to_flush:
        return

    logger.info("Flushing %d job(s) to database on shutdown", len(jobs_to_flush))

    # Build a sync URL from the async one
    db_url = settings.resolved_database_url
    sync_url = db_url.replace("+aiosqlite", "").replace("+asyncpg", "")
    engine = create_engine(sync_url)

    try:
        with Session(engine) as db:
            for job_id, state in jobs_to_flush.items():
                job = db.get(Job, job_id)
                if not job:
                    continue

                process = state["process"]
                output = state["output"]
                exit_code = state.get("exit_code")

                # Determine final status
                if process.poll() is None:
                    # Still running at shutdown — kill it and mark interrupted
                    try:
                        _terminate_process_tree(process, timeout=3)
                    except Exception:
                        try:
                            process.kill()
                        except Exception:
                            pass
                    job.status = "interrupted"
                    job.output = output + "\n[Breachwright shut down while scan was running]"
                    job.exit_code = -2
                elif exit_code == 0:
                    job.status = "complete"
                    job.output = output
                    job.exit_code = 0
                else:
                    job.status = state.get("status", "failed")
                    job.output = output
                    job.exit_code = exit_code

                job.completed_at = state.get("completed_at") or datetime.now(timezone.utc)

            db.commit()
            logger.info("Job flush complete")
    except Exception as e:
        logger.error("Failed to flush jobs on shutdown: %s", e)
    finally:
        engine.dispose()
        for job_id in jobs_to_flush:
            cleanup_job(job_id)
