import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional
from urllib.parse import urlparse

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_admin
from app.auth.models import User
from app.engagements.models import AppSetting
from app.ai.prompts.templates import (
    ANALYSIS_SYSTEM_PROMPT, ATTACK_PATH_SYSTEM_PROMPT, REPORT_SYSTEM_PROMPT
)
from app.gap_detection.service import GAP_ANALYSIS_PROMPT
from app.narrative.service import NARRATIVE_SYSTEM_PROMPT

router = APIRouter(prefix="/api/settings", tags=["settings"])

DEFAULTS = {
    "prompt_analysis": ANALYSIS_SYSTEM_PROMPT,
    "prompt_attack_paths": ATTACK_PATH_SYSTEM_PROMPT,
    "prompt_reports": REPORT_SYSTEM_PROMPT,
    "prompt_gap_analysis": GAP_ANALYSIS_PROMPT,
    "prompt_narrative": NARRATIVE_SYSTEM_PROMPT,
}


class SettingUpdate(BaseModel):
    value: str = Field(max_length=200000)


@router.get("/prompts")
async def get_prompts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prompts = {}
    for key, default in DEFAULTS.items():
        result = await db.execute(select(AppSetting).where(AppSetting.key == key))
        setting = result.scalar_one_or_none()
        prompts[key] = setting.value if setting else default
    return prompts


@router.put("/prompts/{prompt_key}")
async def update_prompt(
    prompt_key: str,
    body: SettingUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if prompt_key not in DEFAULTS:
        raise HTTPException(status_code=400, detail=f"Unknown prompt key: {prompt_key}")

    result = await db.execute(select(AppSetting).where(AppSetting.key == prompt_key))
    setting = result.scalar_one_or_none()

    if setting:
        setting.value = body.value
    else:
        setting = AppSetting(key=prompt_key, value=body.value)
        db.add(setting)

    await db.flush()
    return {"key": prompt_key, "value": body.value}


@router.post("/prompts/{prompt_key}/reset")
async def reset_prompt(
    prompt_key: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if prompt_key not in DEFAULTS:
        raise HTTPException(status_code=400, detail=f"Unknown prompt key: {prompt_key}")

    result = await db.execute(select(AppSetting).where(AppSetting.key == prompt_key))
    setting = result.scalar_one_or_none()
    if setting:
        await db.delete(setting)

    return {"key": prompt_key, "value": DEFAULTS[prompt_key]}


class ProviderUpdate(BaseModel):
    ai_provider: Optional[
        Literal[
            "anthropic",
            "openai",
            "azure",
            "bedrock",
            "local",
            "ollama",
            "vllm",
            "llamacpp",
            "lmstudio",
        ]
    ] = None
    anthropic_api_key: Optional[str] = Field(default=None, max_length=1000)
    openai_api_key: Optional[str] = Field(default=None, max_length=1000)
    anthropic_model: Optional[str] = Field(default=None, max_length=255)
    openai_model: Optional[str] = Field(default=None, max_length=255)
    azure_openai_api_key: Optional[str] = Field(default=None, max_length=1000)
    azure_openai_endpoint: Optional[str] = Field(default=None, max_length=2000)
    azure_openai_deployment: Optional[str] = Field(default=None, max_length=255)
    azure_openai_api_version: Optional[str] = Field(default=None, max_length=100)
    aws_region: Optional[str] = Field(default=None, max_length=100)
    bedrock_model_id: Optional[str] = Field(default=None, max_length=500)
    local_model_url: Optional[str] = Field(default=None, max_length=2000)
    local_model_name: Optional[str] = Field(default=None, max_length=255)
    local_model_api_key: Optional[str] = Field(default=None, max_length=1000)
    local_model_timeout: Optional[int] = Field(default=None, ge=10, le=600)
    ai_redact_sensitive_data: Optional[bool] = None

    @field_validator("*")
    @classmethod
    def reject_env_control_characters(cls, value):
        if isinstance(value, str) and any(char in value for char in ("\r", "\n", "\x00")):
            raise ValueError("Configuration values cannot contain line breaks or null bytes")
        return value

    @field_validator("local_model_url", "azure_openai_endpoint")
    @classmethod
    def validate_local_model_url(cls, value):
        if value is None:
            return value
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Model endpoint must be an HTTP or HTTPS URL")
        return value


@router.get("/provider")
async def get_provider_config(
    current_user: User = Depends(get_current_user),
):
    from app.config import settings as cfg
    from app.ai.model_defaults import RECOMMENDED_MODELS
    provider_name = cfg.ai_provider.lower()
    if provider_name in {"ollama", "vllm", "llamacpp", "lmstudio"}:
        provider_name = "local"
    return {
        "ai_provider": provider_name,
        "recommended_models": RECOMMENDED_MODELS,
        "anthropic_model": cfg.anthropic_model,
        "openai_model": cfg.openai_model,
        "has_anthropic_key": bool(cfg.anthropic_api_key),
        "has_openai_key": bool(cfg.openai_api_key),
        "azure_openai_endpoint": cfg.azure_openai_endpoint,
        "azure_openai_deployment": cfg.azure_openai_deployment,
        "azure_openai_api_version": cfg.azure_openai_api_version,
        "has_azure_openai_key": bool(cfg.azure_openai_api_key),
        "aws_region": cfg.aws_region,
        "bedrock_model_id": cfg.bedrock_model_id,
        "local_model_url": cfg.local_model_url,
        "local_model_name": cfg.local_model_name,
        "local_model_timeout": cfg.local_model_timeout,
        "has_local_key": bool(cfg.local_model_api_key),
        "ai_redact_sensitive_data": cfg.ai_redact_sensitive_data,
    }


@router.put("/provider")
async def update_provider_config(
    body: ProviderUpdate,
    admin: User = Depends(require_admin),
):
    """Update AI provider settings in the .env file."""
    import os
    import tempfile
    from pathlib import Path
    from app.config import settings as cfg, find_env_file

    env_path = find_env_file()
    if not env_path:
        env_path = os.path.join(cfg.data_dir, ".env")
        Path(env_path).parent.mkdir(parents=True, exist_ok=True)

    # Read existing
    env_lines = []
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            env_lines = f.readlines()

    # Update values
    updates = {}
    if body.ai_provider is not None:
        updates["AI_PROVIDER"] = body.ai_provider
    if body.anthropic_api_key is not None:
        updates["ANTHROPIC_API_KEY"] = body.anthropic_api_key
    if body.openai_api_key is not None:
        updates["OPENAI_API_KEY"] = body.openai_api_key
    if body.anthropic_model is not None:
        updates["ANTHROPIC_MODEL"] = body.anthropic_model
    if body.openai_model is not None:
        updates["OPENAI_MODEL"] = body.openai_model
    if body.azure_openai_api_key is not None:
        updates["AZURE_OPENAI_API_KEY"] = body.azure_openai_api_key
    if body.azure_openai_endpoint is not None:
        updates["AZURE_OPENAI_ENDPOINT"] = body.azure_openai_endpoint
    if body.azure_openai_deployment is not None:
        updates["AZURE_OPENAI_DEPLOYMENT"] = body.azure_openai_deployment
    if body.azure_openai_api_version is not None:
        updates["AZURE_OPENAI_API_VERSION"] = body.azure_openai_api_version
    if body.aws_region is not None:
        updates["AWS_REGION"] = body.aws_region
    if body.bedrock_model_id is not None:
        updates["BEDROCK_MODEL_ID"] = body.bedrock_model_id
    if body.local_model_url is not None:
        updates["LOCAL_MODEL_URL"] = body.local_model_url
    if body.local_model_name is not None:
        updates["LOCAL_MODEL_NAME"] = body.local_model_name
    if body.local_model_api_key is not None:
        updates["LOCAL_MODEL_API_KEY"] = body.local_model_api_key
    if body.local_model_timeout is not None:
        updates["LOCAL_MODEL_TIMEOUT"] = str(body.local_model_timeout)
    if body.ai_redact_sensitive_data is not None:
        updates["AI_REDACT_SENSITIVE_DATA"] = str(body.ai_redact_sensitive_data).lower()

    # Apply updates to env lines
    existing_keys = set()
    new_lines = []
    for line in env_lines:
        key = line.split("=")[0].strip() if "=" in line else ""
        if key in updates:
            new_lines.append(f"{key}={json.dumps(str(updates[key]))}\n")
            existing_keys.add(key)
        else:
            new_lines.append(line)

    # Add new keys
    for key, val in updates.items():
        if key not in existing_keys:
            new_lines.append(f"{key}={json.dumps(str(val))}\n")

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=os.path.dirname(env_path),
            prefix=".env.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.writelines(new_lines)
            temporary_path = temporary.name
        try:
            os.chmod(temporary_path, 0o600)
        except OSError:
            pass
        os.replace(temporary_path, env_path)
        temporary_path = None
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)

    return {"status": "updated", "note": "Restart Breachwright for changes to take effect"}

@router.get("/local-model/status")
async def check_local_model_status(
    current_user: User = Depends(get_current_user),
):
    """Check if local model server is reachable and list available models."""
    from app.ai.local_provider import check_local_server
    from app.config import settings as cfg
    return await check_local_server(cfg.local_model_url)
