"""Tested AI model defaults and compatibility helpers.

Provider model catalogs change independently of Breachwright releases. Keep
the simple setup path on a tested model while preserving explicit overrides
for operators who need a different model or deployment.
"""

RECOMMENDED_ANTHROPIC_MODEL = "claude-sonnet-5"
RECOMMENDED_OPENAI_MODEL = "gpt-5.6-terra"
AZURE_OPENAI_V1 = "v1"

RECOMMENDED_MODELS = {
    "anthropic": RECOMMENDED_ANTHROPIC_MODEL,
    "openai": RECOMMENDED_OPENAI_MODEL,
}

LEGACY_ANTHROPIC_DEFAULTS = {
    "claude-sonnet-4-20250514",
}
LEGACY_OPENAI_DEFAULTS = {
    "gpt-4o",
}
LEGACY_AZURE_API_DEFAULTS = {
    "2024-02-15-preview",
}


def uses_claude_5(model: str) -> bool:
    """Return whether a provider model identifier targets Claude 5."""
    return "claude-" in model.lower() and "-5" in model.lower()


def uses_openai_responses(model: str) -> bool:
    """Use the Responses API for current GPT-5-family models."""
    return model.lower().startswith("gpt-5")
