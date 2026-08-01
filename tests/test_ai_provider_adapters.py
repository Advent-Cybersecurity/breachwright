import unittest
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ai.anthropic import AnthropicProvider
from app.ai.bedrock import BedrockProvider
from app.ai.local_provider import LocalProvider
from app.ai.model_defaults import (
    RECOMMENDED_ANTHROPIC_MODEL,
    RECOMMENDED_OPENAI_MODEL,
)
from app.ai.openai_provider import AzureOpenAIProvider, OpenAIProvider
from app.config import Settings


class AIProviderAdapterTests(unittest.IsolatedAsyncioTestCase):
    def test_legacy_defaults_are_normalized_to_tested_recommendations(self):
        settings = Settings(
            _env_file=None,
            anthropic_model="claude-sonnet-4-20250514",
            openai_model="gpt-4o",
            azure_openai_api_version="2024-02-15-preview",
        )
        self.assertEqual(settings.anthropic_model, RECOMMENDED_ANTHROPIC_MODEL)
        self.assertEqual(settings.openai_model, RECOMMENDED_OPENAI_MODEL)
        self.assertEqual(settings.azure_openai_api_version, "v1")

    async def test_claude_5_omits_incompatible_temperature(self):
        client = MagicMock()
        client.messages.create = AsyncMock(
            return_value=SimpleNamespace(
                content=[SimpleNamespace(type="text", text="analysis")]
            )
        )
        with patch("app.ai.anthropic.anthropic.AsyncAnthropic", return_value=client):
            provider = AnthropicProvider("test-key")
            result = await provider.complete("system", "evidence", temperature=0.2)

        self.assertEqual(result, "analysis")
        request = client.messages.create.await_args.kwargs
        self.assertEqual(request["model"], RECOMMENDED_ANTHROPIC_MODEL)
        self.assertNotIn("temperature", request)

    async def test_anthropic_override_preserves_legacy_sampling(self):
        client = MagicMock()
        client.messages.create = AsyncMock(
            return_value=SimpleNamespace(
                content=[SimpleNamespace(type="text", text="analysis")]
            )
        )
        with patch("app.ai.anthropic.anthropic.AsyncAnthropic", return_value=client):
            provider = AnthropicProvider("test-key", model="claude-sonnet-4-6")
            await provider.complete("system", "evidence", temperature=0.2)

        self.assertEqual(client.messages.create.await_args.kwargs["temperature"], 0.2)

    async def test_recommended_openai_model_uses_responses_without_sampling(self):
        client = MagicMock()
        client.responses.create = AsyncMock(
            return_value=SimpleNamespace(output_text="analysis")
        )
        with patch("app.ai.openai_provider.AsyncOpenAI", return_value=client):
            provider = OpenAIProvider("test-key")
            result = await provider.complete("system", "evidence", temperature=0.2)

        self.assertEqual(result, "analysis")
        request = client.responses.create.await_args.kwargs
        self.assertEqual(request["model"], RECOMMENDED_OPENAI_MODEL)
        self.assertEqual(request["reasoning"], {"effort": "none"})
        self.assertEqual(request["max_output_tokens"], 4096)
        self.assertNotIn("temperature", request)
        client.chat.completions.create.assert_not_called()

    async def test_openai_legacy_override_retains_chat_completions(self):
        client = MagicMock()
        client.chat.completions.create = AsyncMock(
            return_value=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="analysis"))]
            )
        )
        with patch("app.ai.openai_provider.AsyncOpenAI", return_value=client):
            provider = OpenAIProvider("test-key", model="gpt-4.1")
            result = await provider.complete("system", "evidence", temperature=0.2)

        self.assertEqual(result, "analysis")
        request = client.chat.completions.create.await_args.kwargs
        self.assertEqual(request["temperature"], 0.2)
        self.assertEqual(request["max_tokens"], 4096)

    async def test_azure_v1_uses_current_base_url_and_responses(self):
        client = MagicMock()
        client.responses.create = AsyncMock(
            return_value=SimpleNamespace(output_text="analysis")
        )
        with patch("app.ai.openai_provider.AsyncOpenAI", return_value=client) as factory:
            provider = AzureOpenAIProvider(
                "test-key",
                "https://example.openai.azure.com",
                "breachwright-model",
            )
            result = await provider.complete("system", "evidence")

        self.assertEqual(result, "analysis")
        self.assertEqual(
            factory.call_args.kwargs["base_url"],
            "https://example.openai.azure.com/openai/v1/",
        )
        self.assertEqual(
            client.responses.create.await_args.kwargs["model"],
            "breachwright-model",
        )

    async def test_azure_dated_override_retains_legacy_client(self):
        client = MagicMock()
        client.chat.completions.create = AsyncMock(
            return_value=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="analysis"))]
            )
        )
        with patch(
            "app.ai.openai_provider.AsyncAzureOpenAI", return_value=client
        ) as factory:
            provider = AzureOpenAIProvider(
                "test-key",
                "https://example.openai.azure.com",
                "breachwright-model",
                api_version="2025-04-01-preview",
            )
            result = await provider.complete("system", "evidence")

        self.assertEqual(result, "analysis")
        self.assertEqual(factory.call_args.kwargs["api_version"], "2025-04-01-preview")
        client.chat.completions.create.assert_awaited_once()

    def test_provider_specific_models_are_required_when_they_cannot_be_inferred(self):
        with self.assertRaisesRegex(ValueError, "BEDROCK_MODEL_ID"):
            BedrockProvider(model_id="")
        with self.assertRaisesRegex(ValueError, "LOCAL_MODEL_NAME"):
            LocalProvider(model="")


if __name__ == "__main__":
    unittest.main()
