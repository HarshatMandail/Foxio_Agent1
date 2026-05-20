# llm.py — Azure OpenAI Client with Cost Controls
import os
import logging
from functools import lru_cache

from openai import AsyncAzureOpenAI
from dotenv import load_dotenv

from .cache import get_cached_response, save_to_cache
from .cost_tracker import (
    get_session,
    estimate_tokens,
    MAX_TOKENS_PER_REQUEST,
)

load_dotenv()

logger = logging.getLogger(__name__)

# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")

# Tiered deployments — use mini for simple tasks, full for complex analysis
AZURE_DEPLOYMENT_FULL = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
AZURE_DEPLOYMENT_MINI = os.getenv("AZURE_OPENAI_DEPLOYMENT_MINI", "gpt-4o-mini")

# Token optimization
MAX_COMPLETION_TOKENS = int(os.getenv("MAX_COMPLETION_TOKENS", "2048"))
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))

# Feature flags
ENABLE_CACHE = os.getenv("ENABLE_LLM_CACHE", "true").lower() == "true"
ENABLE_BUDGET_CHECK = os.getenv("ENABLE_BUDGET_CHECK", "true").lower() == "true"


def _validate_config() -> None:
    """Validate Azure OpenAI environment variables are set."""
    if not AZURE_OPENAI_ENDPOINT:
        raise ValueError("AZURE_OPENAI_ENDPOINT is not set.")
    if not AZURE_OPENAI_API_KEY:
        raise ValueError("AZURE_OPENAI_API_KEY is not set.")


@lru_cache(maxsize=1)
def get_azure_client() -> AsyncAzureOpenAI:
    """Create and cache a singleton Azure OpenAI async client."""
    _validate_config()

    client = AsyncAzureOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
        max_retries=3,
        timeout=60.0,
    )

    logger.info(f"🤖 Azure OpenAI client initialized — {AZURE_OPENAI_ENDPOINT[:40]}...")
    return client


def _truncate_input(text: str, max_tokens: int) -> str:
    """Truncate input text to stay within token budget."""
    estimated = estimate_tokens(text)
    if estimated <= max_tokens:
        return text

    # Truncate to fit (4 chars ≈ 1 token)
    max_chars = max_tokens * 4
    truncated = text[:max_chars]
    logger.warning(
        f"✂️ Input truncated: {estimated} → ~{max_tokens} tokens "
        f"({len(text)} → {max_chars} chars)"
    )
    return truncated


async def analyze_with_llm(
    system_prompt: str,
    user_message: str,
    use_mini: bool = False,
) -> str:
    """
    Send a prompt to Azure OpenAI with full cost controls.

    Features:
    - Cache check (skip LLM if same request was made recently)
    - Budget enforcement (reject if session over budget)
    - Input truncation (stay within token limits)
    - Token usage logging

    Args:
        system_prompt: System instruction for the LLM.
        user_message: User content to analyze.
        use_mini: If True, use GPT-4o-mini (cheaper, faster) instead of GPT-4o.
    """
    session = get_session()

    # 1. Budget check
    if ENABLE_BUDGET_CHECK and session.is_over_budget():
        raise RuntimeError(
            f"💸 Session budget exceeded (${session.total_cost_usd:.4f}). "
            f"Increase MAX_COST_PER_SESSION_USD or reset session."
        )

    # 2. Cache check
    if ENABLE_CACHE:
        cached = get_cached_response(system_prompt, user_message)
        if cached:
            session.record_cache_hit()
            return cached

    # 3. Truncate input to stay within token budget
    input_budget = MAX_TOKENS_PER_REQUEST - MAX_COMPLETION_TOKENS - estimate_tokens(system_prompt)
    user_message = _truncate_input(user_message, max(input_budget, 1000))

    # 4. Select model tier
    deployment = AZURE_DEPLOYMENT_MINI if use_mini else AZURE_DEPLOYMENT_FULL
    logger.info(f"🧠 Using model: {deployment}")

    # 5. Call Azure OpenAI
    client = get_azure_client()

    response = await client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=TEMPERATURE,
        max_tokens=MAX_COMPLETION_TOKENS,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content or ""
    prompt_tokens = response.usage.prompt_tokens
    completion_tokens = response.usage.completion_tokens

    # 6. Track cost
    session.record_call(deployment, prompt_tokens, completion_tokens)

    logger.info(
        f"📊 Tokens — In: {prompt_tokens} | Out: {completion_tokens} | "
        f"Total: {prompt_tokens + completion_tokens}"
    )

    # 7. Cache the response
    if ENABLE_CACHE:
        save_to_cache(
            system_prompt,
            user_message,
            content,
            tokens_used=prompt_tokens + completion_tokens,
        )

    return content


async def analyze_with_llm_stream(
    system_prompt: str,
    user_message: str,
    use_mini: bool = False,
) -> str:
    """
    Stream response from Azure OpenAI with cost controls.

    Use for long-form outputs where progressive results are needed.
    """
    session = get_session()

    if ENABLE_BUDGET_CHECK and session.is_over_budget():
        raise RuntimeError("💸 Session budget exceeded.")

    input_budget = MAX_TOKENS_PER_REQUEST - MAX_COMPLETION_TOKENS - estimate_tokens(system_prompt)
    user_message = _truncate_input(user_message, max(input_budget, 1000))

    deployment = AZURE_DEPLOYMENT_MINI if use_mini else AZURE_DEPLOYMENT_FULL
    client = get_azure_client()

    stream = await client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=TEMPERATURE,
        max_tokens=MAX_COMPLETION_TOKENS,
        stream=True,
    )

    chunks = []
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            chunks.append(chunk.choices[0].delta.content)

    result = "".join(chunks)

    # Estimate tokens for streaming (no usage object available)
    est_prompt = estimate_tokens(system_prompt + user_message)
    est_completion = estimate_tokens(result)
    session.record_call(deployment, est_prompt, est_completion)

    return result
