import json
import logging
from app.ai.model_defaults import uses_claude_5
from app.ai.provider import AIProvider

logger = logging.getLogger(__name__)


class BedrockProvider(AIProvider):
    """AWS Bedrock adapter.

    Uses the Bedrock converse API to support Claude and other
    Bedrock-hosted models. Requires boto3 installed and AWS credentials
    in the environment (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, or IAM role).
    """

    def __init__(self, region: str = "us-east-1", model_id: str = ""):
        if not model_id:
            raise ValueError(
                "BEDROCK_MODEL_ID is required when AI_PROVIDER=bedrock. "
                "Choose a model or inference profile available in your AWS region."
            )
        try:
            import boto3
        except ImportError:
            raise RuntimeError(
                "boto3 is required for the Bedrock provider. "
                "Install it with: pip install boto3"
            )
        self._client = boto3.client("bedrock-runtime", region_name=region)
        self._model_id = model_id

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> str:
        import asyncio
        loop = asyncio.get_event_loop()
        inference_config = {"maxTokens": max_tokens}
        if not uses_claude_5(self._model_id):
            inference_config["temperature"] = temperature
        response = await loop.run_in_executor(
            None,
            lambda: self._client.converse(
                modelId=self._model_id,
                system=[{"text": system_prompt}],
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": user_message}],
                    }
                ],
                inferenceConfig=inference_config,
            ),
        )
        return response["output"]["message"]["content"][0]["text"]

    def name(self) -> str:
        return f"Bedrock ({self._model_id})"
