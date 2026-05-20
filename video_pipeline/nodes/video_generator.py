"""
Video clip generation orchestrator.

Delegates to the xAI SDK adapter with retry logic
(exponential backoff) and graceful failure per clip.
"""

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger

from adapters import get_adapter
from config.settings import settings
from core.registry import model_registry

NON_RETRYABLE_KEYWORDS = {"moderation", "invalid_argument", "permission_denied", "invalid"}


async def generate_clip(
    step_index: int,
    prompt: str,
    model_name: str | None = None,
    duration: int = 6,
    aspect_ratio: str = "16:9",
    resolution: str = "480p",
    start_image: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Generate a single video clip with retry logic.

    Returns a dict with clip metadata on success, or error info on failure.
    Non-retryable errors (moderation, invalid args) fail immediately.
    """
    # Validate prompt before any API call
    if not prompt or not prompt.strip():
        logger.error(f"[Step {step_index}] Empty prompt — skipping to save credits.")
        return {
            "step_index": step_index,
            "status": "failed",
            "error": "Empty prompt",
        }

    resolved_model_name = model_name or settings.default_model
    model = model_registry.get(resolved_model_name)
    clip_duration = max(1, min(duration, model.max_duration, settings.max_clip_duration))

    output_path = settings.clip_output_dir / f"clip_{step_index:03d}.mp4"
    adapter = get_adapter()

    logger.info(
        f"[Step {step_index}] Generating clip | model={model.name} | "
        f"duration={clip_duration}s | aspect_ratio={aspect_ratio}"
    )

    last_error = ""

    for attempt in range(1, settings.max_retries + 1):
        try:
            result = await adapter.generate(
                model=model,
                prompt=prompt,
                duration=clip_duration,
                output_path=output_path,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                start_image=start_image,
                dry_run=dry_run or settings.dry_run,
            )

            logger.success(f"[Step {step_index}] Clip generated: {output_path}")

            return {
                "step_index": step_index,
                "status": result.get("status", "success"),
                "path": str(output_path),
                "model": model.name,
                "duration": clip_duration,
                "cost_usd": result.get("cost_usd"),
            }

        except ValueError as e:
            # Validation errors are non-retryable
            last_error = str(e)
            logger.error(f"[Step {step_index}] Validation error: {last_error}")
            break

        except Exception as e:
            last_error = str(e)
            error_lower = last_error.lower()

            # Check for non-retryable errors
            if any(keyword in error_lower for keyword in NON_RETRYABLE_KEYWORDS):
                logger.error(
                    f"[Step {step_index}] Non-retryable error: {last_error}"
                )
                break

            delay = settings.retry_base_delay * (2 ** (attempt - 1))
            logger.warning(
                f"[Step {step_index}] Attempt {attempt}/{settings.max_retries} "
                f"failed: {last_error}. Retrying in {delay:.1f}s..."
            )
            if attempt < settings.max_retries:
                await asyncio.sleep(delay)

    logger.error(
        f"[Step {step_index}] All {settings.max_retries} attempts failed. "
        f"Last error: {last_error}"
    )
    return {
        "step_index": step_index,
        "status": "failed",
        "error": last_error or f"Failed after {settings.max_retries} retries",
    }
