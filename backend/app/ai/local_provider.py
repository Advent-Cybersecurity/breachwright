"""Local / Self-Hosted Model Provider.

Supports any OpenAI-compatible API endpoint, which covers:
  - Ollama (http://localhost:11434/v1)
  - vLLM (http://localhost:8000/v1)
  - llama.cpp server (http://localhost:8080/v1)
  - LM Studio (http://localhost:1234/v1)
  - LocalAI (http://localhost:8080/v1)
  - text-generation-webui with openai extension

Also supports Ollama's native API for users who prefer it.

No API key required. No data leaves the machine.
"""
import logging
import httpx
from app.ai.provider import AIProvider

logger = logging.getLogger(__name__)

# Default endpoints for common local servers
KNOWN_ENDPOINTS = {
    "ollama": "http://localhost:11434",
    "vllm": "http://localhost:8000",
    "llamacpp": "http://localhost:8080",
    "lmstudio": "http://localhost:1234",
    "localai": "http://localhost:8080",
}


class LocalProvider(AIProvider):
    """Self-hosted model provider using OpenAI-compatible API.

    Works with any server that implements the /v1/chat/completions
    endpoint (which is nearly all of them now).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "",
        api_key: str = "not-needed",
        timeout: int = 120,
        api_format: str = "openai",
    ):
        if not model:
            raise ValueError(
                "LOCAL_MODEL_NAME is required when AI_PROVIDER=local. "
                "Connect to the server and select one of its installed models."
            )
        # Normalize base URL
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key or "not-needed"
        self._timeout = timeout
        self._api_format = api_format  # "openai" or "ollama"

        # Auto-detect: if base_url looks like Ollama default and no /v1, use Ollama native
        if "11434" in self._base_url and "/v1" not in self._base_url and api_format == "openai":
            # Ollama supports both, but /v1 is more standard
            self._chat_url = f"{self._base_url}/v1/chat/completions"
        elif "/v1" in self._base_url:
            self._chat_url = f"{self._base_url}/chat/completions"
        else:
            self._chat_url = f"{self._base_url}/v1/chat/completions"

        logger.info("LocalProvider initialized: %s model=%s", self._chat_url, self._model)

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        headers = {
            "Content-Type": "application/json",
        }
        # Some servers want an auth header even if it's dummy
        if self._api_key and self._api_key != "not-needed":
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._chat_url,
                    json=payload,
                    headers=headers,
                )

                if response.status_code != 200:
                    error_text = response.text[:500]
                    logger.error(
                        "Local model error (%d): %s",
                        response.status_code, error_text,
                    )
                    raise RuntimeError(
                        f"Local model returned {response.status_code}. "
                        f"Is {self._model} running? Check your local server. "
                        f"Error: {error_text}"
                    )

                data = response.json()

                # OpenAI-compatible format
                if "choices" in data:
                    return data["choices"][0]["message"]["content"]

                # Ollama native format fallback
                if "message" in data:
                    return data["message"]["content"]

                # Raw response fallback
                if "response" in data:
                    return data["response"]

                raise RuntimeError(
                    f"Unexpected response format from local model: {list(data.keys())}"
                )

        except httpx.ConnectError:
            raise RuntimeError(
                f"Cannot connect to local model at {self._base_url}. "
                f"Make sure your model server is running.\n\n"
                f"Quick start:\n"
                f"  Ollama:    ollama serve && ollama pull {self._model}\n"
                f"  vLLM:      python -m vllm.entrypoints.openai.api_server --model {self._model}\n"
                f"  LM Studio: Start server in LM Studio settings"
            )
        except httpx.ReadTimeout:
            raise RuntimeError(
                f"Local model timed out after {self._timeout}s. "
                f"This usually means the model is too large for your hardware. "
                f"Try a smaller model or increase the timeout in settings."
            )

    def name(self) -> str:
        return f"Local ({self._model} @ {self._base_url})"


async def check_local_server(base_url: str = "http://localhost:11434") -> dict:
    """Check if a local model server is reachable and list available models.

    Returns: {"online": bool, "models": [...], "server_type": str, "error": str}
    """
    base_url = base_url.rstrip("/")
    result = {"online": False, "models": [], "server_type": "unknown", "error": None}

    async with httpx.AsyncClient(timeout=5) as client:
        # Try Ollama's native model list endpoint
        try:
            resp = await client.get(f"{base_url}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                result["online"] = True
                result["server_type"] = "ollama"
                result["models"] = [
                    {
                        "name": m["name"],
                        "size": m.get("size"),
                        "modified": m.get("modified_at"),
                    }
                    for m in data.get("models", [])
                ]
                return result
        except Exception:
            pass

        # Try OpenAI-compatible /v1/models
        try:
            resp = await client.get(f"{base_url}/v1/models")
            if resp.status_code == 200:
                data = resp.json()
                result["online"] = True
                result["server_type"] = "openai_compatible"
                result["models"] = [
                    {"name": m.get("id", m.get("name", "unknown"))}
                    for m in data.get("data", [])
                ]
                return result
        except Exception:
            pass

        # Try root endpoint for basic health
        try:
            resp = await client.get(base_url)
            if resp.status_code == 200:
                result["online"] = True
                result["server_type"] = "unknown"
                return result
        except Exception as e:
            result["error"] = str(e)

    return result
