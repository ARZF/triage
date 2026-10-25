import json
import logging

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """A provider failure with only a safe outcome category."""


def chat_completion(
    settings: Settings, messages: list[dict], *, transport: httpx.BaseTransport | None = None
) -> dict:
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"} if settings.llm_api_key else {}
    try:
        with httpx.Client(timeout=settings.llm_timeout_seconds, transport=transport) as client:
            response = client.post(
                settings.llm_base_url.rstrip("/") + "/chat/completions",
                headers=headers,
                json={
                    "model": settings.llm_model, "messages": messages, "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
    except httpx.HTTPStatusError:
        logger.warning("http_error")
        raise LLMError("http_error") from None
    except (httpx.HTTPError, httpx.InvalidURL, UnicodeError):
        logger.warning("transport_error")
        raise LLMError("transport_error") from None
    try:
        content = response.json()["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError
    except (ValueError, TypeError, KeyError, IndexError):
        logger.warning("invalid_response")
        raise LLMError("invalid_response") from None
    logger.info("success")
    return result
