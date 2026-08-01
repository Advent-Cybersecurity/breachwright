from openai import AsyncOpenAI, AsyncAzureOpenAI
from app.ai.model_defaults import (
    AZURE_OPENAI_V1,
    RECOMMENDED_OPENAI_MODEL,
    uses_openai_responses,
)
from app.ai.provider import AIProvider


class OpenAIProvider(AIProvider):
    """OpenAI adapter with current Responses support and legacy compatibility."""

    def __init__(self, api_key: str, model: str = RECOMMENDED_OPENAI_MODEL):
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required when AI_PROVIDER=openai")
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> str:
        if uses_openai_responses(self._model):
            response = await self._client.responses.create(
                model=self._model,
                instructions=system_prompt,
                input=user_message,
                max_output_tokens=max_tokens,
                reasoning={"effort": "none"},
            )
            return response.output_text

        response = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return response.choices[0].message.content

    def name(self) -> str:
        return f"OpenAI ({self._model})"


class AzureOpenAIProvider(AIProvider):
    """Azure OpenAI v1 adapter with dated-API compatibility."""

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        deployment: str,
        api_version: str = AZURE_OPENAI_V1,
    ):
        if not all([api_key, endpoint, deployment]):
            raise ValueError(
                "AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, and "
                "AZURE_OPENAI_DEPLOYMENT are required when AI_PROVIDER=azure"
            )
        self._api_version = api_version
        if api_version.lower() == AZURE_OPENAI_V1:
            base_url = endpoint.rstrip("/")
            if not base_url.lower().endswith("/openai/v1"):
                base_url = f"{base_url}/openai/v1"
            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url=f"{base_url}/",
            )
        else:
            self._client = AsyncAzureOpenAI(
                api_key=api_key,
                azure_endpoint=endpoint,
                api_version=api_version,
            )
        self._deployment = deployment

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> str:
        if self._api_version.lower() == AZURE_OPENAI_V1:
            response = await self._client.responses.create(
                model=self._deployment,
                instructions=system_prompt,
                input=user_message,
                max_output_tokens=max_tokens,
            )
            return response.output_text

        response = await self._client.chat.completions.create(
            model=self._deployment,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return response.choices[0].message.content

    def name(self) -> str:
        return f"Azure OpenAI ({self._deployment})"
