"""Azure OpenAI access — the single LLM provider for this project."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, TypeVar

from openai import AsyncAzureOpenAI, OpenAIError
from pydantic import BaseModel, ValidationError

from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMNotConfiguredError(RuntimeError):
    pass


@lru_cache
def get_client() -> AsyncAzureOpenAI:
    if not settings.azure_openai_endpoint or not settings.azure_openai_api_key:
        raise LLMNotConfiguredError(
            "AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY must be set."
        )
    return AsyncAzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        timeout=30.0,
        max_retries=2,
    )


async def complete(
    *,
    system: str,
    messages: list[dict[str, str]],
    temperature: float = 0.3,
    max_tokens: int = 400,
) -> str:
    """Plain chat completion returning the assistant's text."""
    response = await get_client().chat.completions.create(
        model=settings.azure_openai_chat_deployment,
        messages=[{"role": "system", "content": system}, *messages],  # type: ignore[arg-type]
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return (response.choices[0].message.content or "").strip()


async def complete_structured(
    *,
    system: str,
    messages: list[dict[str, str]],
    schema: type[T],
    temperature: float = 0.0,
    max_tokens: int = 500,
) -> T:
    """Chat completion coerced into a pydantic model.

    Uses JSON mode plus an explicit schema in the prompt rather than the
    ``response_format=<pydantic model>`` helper, because JSON mode is supported
    across every Azure OpenAI API version we might be pointed at.
    """
    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    system_with_schema = (
        f"{system}\n\n"
        "Reply with a single JSON object and nothing else. It must validate "
        f"against this JSON Schema:\n{schema_json}"
    )
    raw = ""
    try:
        response = await get_client().chat.completions.create(
            model=settings.azure_openai_chat_deployment,
            messages=[{"role": "system", "content": system_with_schema}, *messages],  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or ""
        return schema.model_validate_json(raw)
    except (ValidationError, json.JSONDecodeError) as exc:
        logger.warning("Structured completion failed to validate: %s | raw=%r", exc, raw[:500])
        raise
    except OpenAIError as exc:
        logger.error("Azure OpenAI request failed: %s", exc)
        raise


async def embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch of strings with the configured embedding deployment."""
    if not texts:
        return []
    response = await get_client().embeddings.create(
        model=settings.azure_openai_embedding_deployment,
        input=texts,
    )
    ordered = sorted(response.data, key=lambda item: item.index)
    vectors = [item.embedding for item in ordered]

    expected = settings.embedding_dimensions
    for vector in vectors:
        if len(vector) != expected:
            raise RuntimeError(
                f"Embedding deployment returned {len(vector)} dimensions but the "
                f"database column is {expected}. Set EMBEDDING_DIMENSIONS to "
                f"{len(vector)} and re-run migrations."
            )
    return vectors


def describe_config() -> dict[str, Any]:
    """Non-secret view of the LLM configuration, for /health."""
    return {
        "endpoint_configured": bool(settings.azure_openai_endpoint),
        "api_key_configured": bool(settings.azure_openai_api_key),
        "chat_deployment": settings.azure_openai_chat_deployment,
        "embedding_deployment": settings.azure_openai_embedding_deployment,
        "embedding_dimensions": settings.embedding_dimensions,
    }
