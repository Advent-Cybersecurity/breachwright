import anthropic
from app.ai.provider import AIProvider


class AnthropicProvider(AIProvider):
    """Anthropic Claude API adapter.

    This is the primary/recommended provider. Prompts are tuned for
    Claude Sonnet 4 output quality.
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
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
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text

    def name(self) -> str:
        return f"Anthropic ({self._model})"
