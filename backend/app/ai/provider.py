from abc import ABC, abstractmethod


class AIProvider(ABC):
    """Abstract base class for AI provider integrations.

    All AI-powered features (scan analysis, attack path generation, report
    writing) call through this interface. The active provider is determined
    by the customer's .env configuration.
    """

    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> str:
        """Send a completion request and return the text response."""
        pass

    @abstractmethod
    def name(self) -> str:
        """Return the provider name for logging and display."""
        pass


def get_provider() -> AIProvider:
    """Factory function to instantiate the configured AI provider."""
    from app.config import settings

    provider = settings.ai_provider.lower()

    if provider == "anthropic":
        from app.ai.anthropic import AnthropicProvider
        return AnthropicProvider(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )
    elif provider == "openai":
        from app.ai.openai_provider import OpenAIProvider
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )
    elif provider == "azure":
        from app.ai.openai_provider import AzureOpenAIProvider
        return AzureOpenAIProvider(
            api_key=settings.azure_openai_api_key,
            endpoint=settings.azure_openai_endpoint,
            deployment=settings.azure_openai_deployment,
            api_version=settings.azure_openai_api_version,
        )
    elif provider == "bedrock":
        from app.ai.bedrock import BedrockProvider
        return BedrockProvider(
            region=settings.aws_region,
            model_id=settings.bedrock_model_id,
        )
    elif provider in ("local", "ollama", "vllm", "llamacpp", "lmstudio"):
        from app.ai.local_provider import LocalProvider
        return LocalProvider(
            base_url=settings.local_model_url,
            model=settings.local_model_name,
            api_key=settings.local_model_api_key,
            timeout=settings.local_model_timeout,
        )
    else:
        raise ValueError(f"Unknown AI provider: {provider}")
