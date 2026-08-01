import anthropic
from app.ai.model_defaults import RECOMMENDED_ANTHROPIC_MODEL, uses_claude_5
from app.ai.provider import AIProvider


class AnthropicProvider(AIProvider):
    """Anthropic Claude API adapter.

    This is the primary/recommended provider. The default targets the tested
    balanced Claude model while allowing an explicit advanced override.
    """

    def __init__(self, api_key: str, model: str = RECOMMENDED_ANTHROPIC_MODEL):
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when AI_PROVIDER=anthropic")
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> str:
        request = dict(
            model=self._model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        # Claude 5 uses adaptive thinking by default and rejects non-default
        # sampling controls. Older explicit overrides retain prior behavior.
        if not uses_claude_5(self._model):
            request["temperature"] = temperature
        response = await self._client.messages.create(**request)
        text_blocks = [
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        ]
        return "\n".join(text_blocks)

    def name(self) -> str:
        return f"Anthropic ({self._model})"
