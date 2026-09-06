import logging
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from app.config import settings

logger = logging.getLogger("orca")


class GroqClient:
    def __init__(self) -> None:
        self._api_key = settings.GROQ_API_KEY
        self._model = settings.GROQ_MODEL
        self._base_url = "https://api.groq.com/openai/v1"
        self._client: AsyncOpenAI | None = None

    def _ensure_client(self) -> AsyncOpenAI:
        if self._client is None:
            if not self._api_key:
                raise RuntimeError("GROQ_API_KEY is not configured")
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
            )
        return self._client

    def _categorize_failure(self, exc: Exception) -> str:
        error_str = str(exc).lower()
        if "rate limit" in error_str or "429" in error_str or "tokens per day" in error_str:
            return "rate_limited"
        if "timeout" in error_str:
            return "timeout"
        if "api key" in error_str or "401" in error_str or "403" in error_str:
            return "authentication_error"
        if "model not found" in error_str or "404" in error_str:
            return "model_unavailable"
        return "upstream_error"

    async def chat(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str | None = None,
        **kwargs: Any,
    ) -> Any:
        client = self._ensure_client()
        used_model = model or self._model

        logger.debug(
            "Sending chat request to Groq",
            extra={
                "model": used_model,
                "message_count": len(messages),
            },
        )

        try:
            response = await client.chat.completions.create(
                model=used_model,
                messages=messages,
                **kwargs,
            )
        except Exception as exc:
            category = self._categorize_failure(exc)
            logger.error(
                "Groq chat request failed: category=%s, error=%s",
                category,
                exc,
                exc_info=True,
            )
            raise RuntimeError(f"Groq request failed [{category}]: {exc}") from exc

        return response

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None


groq_client = GroqClient()
