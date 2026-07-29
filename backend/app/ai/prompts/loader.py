from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.engagements.models import AppSetting
from app.ai.prompts.templates import (
    ANALYSIS_SYSTEM_PROMPT, ATTACK_PATH_SYSTEM_PROMPT, REPORT_SYSTEM_PROMPT
)

DEFAULTS = {
    "prompt_analysis": ANALYSIS_SYSTEM_PROMPT,
    "prompt_attack_paths": ATTACK_PATH_SYSTEM_PROMPT,
    "prompt_reports": REPORT_SYSTEM_PROMPT,
}


async def get_prompt(db: AsyncSession, key: str) -> str:
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    setting = result.scalar_one_or_none()
    return setting.value if setting else DEFAULTS.get(key, "")
