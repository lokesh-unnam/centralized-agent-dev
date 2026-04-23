"""
Unified LLM Client (OpenAI Strict) - Async Version
Single interface used by all agents.
"""
from __future__ import annotations
import asyncio
from typing import Any
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings

logger = structlog.get_logger(__name__)

def _make_openai_client():
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "The 'openai' package is required. Run: pip install openai"
        )
    if not settings.openai_api_key:
        raise ValueError(
            "OPENAI_API_KEY is not set. Add it to your .env file."
        )
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = _make_openai_client()
        logger.info("llm_client.initialized", provider="openai")
    return _client

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def call(
    system: str,
    user_message: str,
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: int = 0, # Forced to integer for strict API compatibility
) -> str:
    """Unified LLM call using OpenAI (Async)."""
    client = _get_client()
    resolved_model = model or settings.model_strong

    logger.debug("llm_client.call", provider="openai", model=resolved_model,
                 prompt_len=len(user_message))

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: client.chat.completions.create(
                model=resolved_model,
                max_tokens=max_tokens,
                temperature=0, # Fixed: Forced to integer to satisfy strict API validation
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_message},
                ],
            )
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("llm_client.error", error=str(e), model=resolved_model)
        raise

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def call_with_messages(
    system: str,
    messages: list[dict[str, Any]],
    model: str | None = None,
    max_tokens: int = 8192,
) -> str:
    """Multi-turn call using OpenAI (Async)."""
    client = _get_client()
    resolved_model = model or settings.model_strong

    full_messages = [{"role": "system", "content": system}] + messages
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model=resolved_model,
                max_tokens=max_tokens,
                temperature=0, # Fixed: Forced to integer to satisfy strict API validation
                messages=full_messages,
            )
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("llm_client.error_messages", error=str(e), model=resolved_model)
        raise

def get_provider_info() -> dict[str, str]:
    return {
        "provider": "openai",
        "model_strong": settings.model_strong,
        "model_fast": settings.model_fast,
    }
