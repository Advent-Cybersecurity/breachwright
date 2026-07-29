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
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_running_jobs: dict = {}
_lock = threading.Lock()

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
        "cves": {"name": "CVE Detection", "description": "Scan for known CVEs", "cmd": "nuclei -u {target} -t cves/ -o {output_file} -silent"},
        "misconfig": {"name": "Misconfigurations", "description": "Detect common misconfigurations", "cmd": "nuclei -u {target} -t misconfiguration/ -o {output_file} -silent"},
        "exposures": {"name": "Exposures", "description": "Detect exposed panels, files, and data", "cmd": "nuclei -u {target} -t exposures/ -o {output_file} -silent"},
        "all": {"name": "Full Template Scan", "description": "Run all nuclei templates (slow)", "cmd": "nuclei -u {target} -o {output_file} -silent"},
    },
}


def get_presets():
    result = {}
    for tool, presets in TOOL_PRESETS.items():
        available = shutil.which(tool) is not None
        result[tool] = {"available": available, "path": shutil.which(tool) if available else None, "presets": presets}
    return result


def start_job(job_id: str, command: str, tool: str, output_dir: str) -> Optional[int]:
    os.makedirs(output_dir, exist_ok=True)
    logger.info("Starting job %s: %s", job_id, command)
    try:
        process = subprocess.Popen(
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, cwd=output_dir,
            preexec_fn=os.setsid if os.name != "nt" else None,
        )
    except Exception as e:
        logger.error("Failed to start job %s: %s", job_id, e)
        return None

    with _lock:
        _running_jobs[job_id] = {
            "process": process, "output": "", "tool": tool,
            "command": command, "started_at": datetime.now(timezone.utc),
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
                    _running_jobs[job_id]["output"] += line
        process.wait()
    except Exception as e:
        logger.error("Error capturing output for job %s: %s", job_id, e)
    finally:
        with _lock:
            if job_id in _running_jobs:
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
            "output": job["output"],
            "status": job.get("status", "running" if process.poll() is None else "complete"),
            "pid": process.pid,
            "exit_code": job.get("exit_code"),
            "started_at": job["started_at"].isoformat(),
            "completed_at": job.get("completed_at").isoformat() if job.get("completed_at") else None,
        }


def stop_job(job_id: str) -> bool:
    with _lock:
        job = _running_jobs.get(job_id)
        if not job:
            return False
        process = job["process"]
    if process.poll() is not None:
        return False
    try:
        if os.name != "nt":
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        else:
            process.kill()
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
        return _running_jobs.pop(job_id, None)


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
        jobs_to_flush = dict(_running_jobs)

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
                output = state.get("output", "")
                exit_code = state.get("exit_code")

                # Determine final status
                if process.poll() is None:
                    # Still running at shutdown — kill it and mark interrupted
                    try:
                        if os.name != "nt":
                            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                        else:
                            process.terminate()
                        process.wait(timeout=3)
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
