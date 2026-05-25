"""
Video clip generation orchestrator — Edit-Video mode only.

Generates enhanced tutorial clips from real Playwright browser recordings
using Grok Imagine Video's edit-video mode.

Pipeline per clip:
  1. Preprocess raw .webm → .mp4 (convert, trim, normalize)
  2. Build production-grade edit-video prompt
  3. Upload to xAI + call edit-video API
  4. Save enhanced output

Includes per-clip retry (3 attempts) and pipeline-level retry (3 rounds)
for maximum resilience against transient API failures.
"""

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger

from adapters import get_adapter
from adapters.grok_adapter import GrokAdapter
from config.settings import settings
from nodes.utils import preprocess_video_for_grok

NON_RETRYABLE_KEYWORDS = {"moderation", "invalid_argument", "permission_denied", "invalid"}

# Pipeline-level retry for failed clips (on top of per-clip adapter retries)
PIPELINE_RETRY_ATTEMPTS = 3


async def generate_clip_edit_video(
    step_index: int,
    input_video_path: str,
    narration: str = "",
    action: str = "",
    duration: int = 5,
    total_steps: int = 1,
    platform_name: str = "Salesforce",
    aspect_ratio: str = "16:9",
    resolution: str = "480p",
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Generate a single enhanced clip from a real browser recording using edit-video mode.

    Pipeline:
      1. Preprocess raw .webm → .mp4 (convert, trim, normalize FPS/resolution)
      2. Build production-grade edit-video prompt
      3. Upload processed .mp4 to xAI
      4. Call Grok Imagine Video in edit-video mode
      5. Save enhanced output

    Returns a dict with clip metadata on success, or error info on failure.
    """
    video_file = Path(input_video_path)
    if not video_file.exists():
        logger.error(f"[EditVideo Step {step_index}] Input video not found: {input_video_path}")
        return {
            "step_index": step_index,
            "status": "failed",
            "error": f"Input video not found: {input_video_path}",
            "mode": "edit-video",
        }

    # Step 1: Preprocess .webm → .mp4 (convert, trim to 6s, normalize FPS/resolution)
    try:
        processed_path = preprocess_video_for_grok(str(video_file))
        logger.info(
            f"[EditVideo Step {step_index}] Preprocessed: {video_file.name} → {Path(processed_path).name}"
        )
    except RuntimeError as e:
        logger.error(f"[EditVideo Step {step_index}] Preprocessing failed: {e}")
        return {
            "step_index": step_index,
            "status": "failed",
            "error": f"Preprocessing failed: {e}",
            "mode": "edit-video",
        }

    # Step 2: Build the edit-video prompt with full context
    prompt = _build_edit_video_prompt(
        action=action,
        narration=narration,
        step_number=step_index,
        total_steps=total_steps,
        platform_name=platform_name,
    )
    output_path = settings.clip_output_dir / f"clip_{step_index:03d}_edited.mp4"

    adapter = get_adapter()
    if not isinstance(adapter, GrokAdapter):
        logger.error("[EditVideo] Adapter does not support edit-video mode.")
        return {
            "step_index": step_index,
            "status": "failed",
            "error": "Adapter does not support edit-video",
            "mode": "edit-video",
        }

    logger.info(
        f"[EditVideo Step {step_index}] Enhancing clip | "
        f"input={Path(processed_path).name} | duration={duration}s | narration={narration[:60]}"
    )

    last_error = ""

    for attempt in range(1, settings.max_retries + 1):
        try:
            result = await adapter.generate_edit_video(
                input_video_path=processed_path,
                prompt=prompt,
                duration=duration,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                output_path=output_path,
                dry_run=dry_run or settings.dry_run,
            )

            logger.success(f"[EditVideo Step {step_index}] Enhanced clip saved: {output_path}")

            return {
                "step_index": step_index,
                "status": result.get("status", "success"),
                "path": str(output_path),
                "model": "grok-imagine-video",
                "duration": duration,
                "mode": "edit-video",
                "input_video": str(video_file),
                "preprocessed_video": processed_path,
                "cost_usd": result.get("cost_usd"),
            }

        except FileNotFoundError as e:
            last_error = str(e)
            logger.error(f"[EditVideo Step {step_index}] File error: {last_error}")
            break

        except Exception as e:
            last_error = str(e)
            error_lower = last_error.lower()

            if any(keyword in error_lower for keyword in NON_RETRYABLE_KEYWORDS):
                logger.error(
                    f"[EditVideo Step {step_index}] Non-retryable error: {last_error}"
                )
                break

            delay = settings.retry_base_delay * (2 ** (attempt - 1))
            logger.warning(
                f"[EditVideo Step {step_index}] Attempt {attempt}/{settings.max_retries} "
                f"failed: {last_error}. Retrying in {delay:.1f}s..."
            )
            if attempt < settings.max_retries:
                await asyncio.sleep(delay)

    logger.error(
        f"[EditVideo Step {step_index}] All {settings.max_retries} attempts failed. "
        f"Last error: {last_error}"
    )
    return {
        "step_index": step_index,
        "status": "failed",
        "error": last_error or f"Failed after {settings.max_retries} retries",
        "mode": "edit-video",
    }


async def generate_all_clips(
    video_clips: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Generate all enhanced clips from real browser recordings using edit-video mode.

    Each clip is enhanced sequentially with per-clip retry logic.
    After the first pass, failed clips are retried up to PIPELINE_RETRY_ATTEMPTS
    additional rounds with exponential backoff.

    Args:
        video_clips: List of dicts from browser agent with keys:
            - step: int (step number)
            - video_path: str (path to recorded .webm)
            - narration: str (what happens in this step)
            - action: str (the browser action performed)

    Returns:
        List of result dicts with clip metadata.
    """
    results: list[dict[str, Any]] = []

    logger.info(f"[EditVideo Pipeline] Processing {len(video_clips)} real browser recordings...")

    total_steps = len(video_clips)

    # First pass — attempt all clips
    for clip_data in video_clips:
        step_index = clip_data.get("step", 0)
        video_path = clip_data.get("video_path", "")
        narration = clip_data.get("narration", "")
        action = clip_data.get("action", "")
        platform_name = clip_data.get("_platform_name", "Salesforce")
        duration = min(clip_data.get("duration", 5), settings.max_clip_duration)

        result = await generate_clip_edit_video(
            step_index=step_index,
            input_video_path=video_path,
            narration=narration,
            action=action,
            duration=duration,
            total_steps=total_steps,
            platform_name=platform_name,
        )

        results.append(result)

    # Pipeline-level retry — re-attempt failed clips with exponential backoff
    failed_indices = [
        i for i, r in enumerate(results) if r["status"] == "failed"
    ]

    if failed_indices:
        logger.warning(
            f"[EditVideo Pipeline] {len(failed_indices)} clips failed on first pass. "
            f"Starting pipeline-level retry..."
        )

        for retry_round in range(1, PIPELINE_RETRY_ATTEMPTS + 1):
            if not failed_indices:
                break

            delay = settings.retry_base_delay * (2 ** (retry_round - 1))
            logger.info(
                f"[EditVideo Pipeline] Retry round {retry_round}/{PIPELINE_RETRY_ATTEMPTS} | "
                f"{len(failed_indices)} clips to retry | waiting {delay:.1f}s..."
            )
            await asyncio.sleep(delay)

            still_failed = []
            for idx in failed_indices:
                clip_data = video_clips[idx]
                step_index = clip_data.get("step", 0)

                logger.info(
                    f"[EditVideo Pipeline] Retrying step {step_index} "
                    f"(round {retry_round}/{PIPELINE_RETRY_ATTEMPTS})"
                )

                result = await generate_clip_edit_video(
                    step_index=step_index,
                    input_video_path=clip_data.get("video_path", ""),
                    narration=clip_data.get("narration", ""),
                    action=clip_data.get("action", ""),
                    duration=min(clip_data.get("duration", 5), settings.max_clip_duration),
                    total_steps=total_steps,
                    platform_name=clip_data.get("_platform_name", "Salesforce"),
                )

                results[idx] = result

                if result["status"] == "failed":
                    still_failed.append(idx)
                else:
                    logger.success(
                        f"[EditVideo Pipeline] Step {step_index} succeeded on retry round {retry_round}"
                    )

            failed_indices = still_failed

        if failed_indices:
            logger.error(
                f"[EditVideo Pipeline] {len(failed_indices)} clips still failed after "
                f"{PIPELINE_RETRY_ATTEMPTS} retry rounds."
            )

    successful = sum(1 for r in results if r["status"] in ("success", "dry_run"))
    failed = sum(1 for r in results if r["status"] == "failed")
    logger.info(
        f"[EditVideo Pipeline] Complete | "
        f"{successful}/{len(video_clips)} successful | {failed} failed"
    )

    return results


def _build_edit_video_prompt(
    action: str,
    narration: str,
    step_number: int,
    total_steps: int,
    platform_name: str = "Salesforce",
) -> str:
    """
    Production-grade edit-video prompt for SaaS tutorial videos.

    Maximally constrains the model to preserve UI fidelity while only
    allowing cursor smoothing and professional polish improvements.
    """
    return (
        f"EXACT EDIT of this real screen recording of {platform_name}. "
        f"Keep EVERY UI element, text, button, icon, color, layout, font, and data 100% IDENTICAL to the original video. "
        f"DO NOT invent, change, move, add, remove, or hallucinate ANY visual element. "
        f"Only allowed improvements: "
        f"- Make mouse cursor smooth, realistic white arrow with subtle soft shadow. "
        f"- Natural hover for 0.3 seconds then precise click. "
        f"- Smooth 60fps motion, ultra sharp, professional clean SaaS tutorial style. "
        f"Action being performed: {action}. "
        f"Narration context: {narration}. "
        f"This is step {step_number} of {total_steps}. "
        f"No creative freedom. No artifacts. No text overlays. No layout changes. No fake data."
    )
