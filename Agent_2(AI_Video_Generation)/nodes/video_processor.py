"""
Video Processor — Sequential clip enhancement with extend-video continuity.

Processing strategy:
  • Clip 0 → generate_animated_clip() — normal edit/animate mode with user prompt.
  • Clip 1+ → extend_video() — extend from the previous clip's output for smooth continuity.

This ensures the final video has no jumps or style discontinuities between segments.
"""

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger

from adapters import get_adapter
from adapters.grok_adapter import GrokAdapter
from config.settings import settings

NON_RETRYABLE_KEYWORDS = {"moderation", "invalid_argument", "permission_denied", "invalid"}
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0


async def process_clips_sequentially(
    clips: list[dict],
    user_prompt: str,
    platform_name: str = "Salesforce",
) -> list[dict[str, Any]]:
    """
    Process all clips sequentially with extend-video continuity.

    First clip uses animate mode. Every subsequent clip uses extend-video mode,
    passing the previously generated clip as the source for smooth continuation.

    Args:
        clips: List of clip dicts from video_splitter (index, path, duration).
        user_prompt: The user's enhancement/animation prompt.
        platform_name: Platform name for prompt context.

    Returns:
        List of result dicts with status, path, mode for each clip.
    """
    adapter = get_adapter()
    if not isinstance(adapter, GrokAdapter):
        raise RuntimeError("Adapter does not support animate/extend-video modes.")

    results: list[dict[str, Any]] = []
    previous_output_path: str | None = None
    total = len(clips)

    logger.info(f"[Processor] Starting sequential processing of {total} clips...")
    logger.info(f"[Processor] Strategy: Clip 0 = animate | Clips 1-{total-1} = extend-video")

    for i, clip in enumerate(clips):
        clip_path = clip["path"]
        clip_duration = clip.get("duration", 8.0)
        clip_index = clip["index"]

        output_path = settings.clip_output_dir / f"enhanced_{clip_index:03d}.mp4"

        if i == 0:
            logger.info(f"[Processor] Clip {clip_index}/{total-1} — ANIMATE mode")
            result = await _process_with_retry(
                adapter=adapter,
                mode="animate",
                input_video_path=clip_path,
                prompt=_build_animate_prompt(user_prompt, platform_name, clip_index, total),
                duration=round(clip_duration),
                output_path=output_path,
                previous_clip_path=None,
                clip_index=clip_index,
            )
        else:
            logger.info(
                f"[Processor] Clip {clip_index}/{total-1} — EXTEND-VIDEO mode "
                f"(continuing from clip {clip_index - 1})"
            )
            result = await _process_with_retry(
                adapter=adapter,
                mode="extend",
                input_video_path=clip_path,
                prompt=_build_extend_prompt(user_prompt, platform_name, clip_index, total),
                duration=round(clip_duration),
                output_path=output_path,
                previous_clip_path=previous_output_path,
                clip_index=clip_index,
            )

        results.append(result)

        # Update previous_output_path for next iteration's extend-video
        if result["status"] in ("success", "dry_run"):
            previous_output_path = result.get("path", clip_path)
            logger.success(f"[Processor] Clip {clip_index} ✓ ({result['mode']})")
        else:
            # If a clip fails, use the raw input as fallback for continuity
            previous_output_path = clip_path
            logger.warning(
                f"[Processor] Clip {clip_index} ✗ — using raw clip as fallback for next extend"
            )

    successful = sum(1 for r in results if r["status"] in ("success", "dry_run"))
    failed = sum(1 for r in results if r["status"] == "failed")
    logger.info(f"[Processor] Complete | {successful}/{total} success | {failed} failed")

    return results


async def _process_with_retry(
    adapter: GrokAdapter,
    mode: str,
    input_video_path: str,
    prompt: str,
    duration: float,
    output_path: Path,
    previous_clip_path: str | None,
    clip_index: int,
) -> dict[str, Any]:
    """Process a single clip with exponential backoff retry (3 attempts)."""
    last_error = ""

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if mode == "animate":
                result = await adapter.generate_animated_clip(
                    input_video_path=input_video_path,
                    prompt=prompt,
                    duration=min(duration, settings.max_clip_duration),
                    output_path=output_path,
                )
            else:
                result = await adapter.extend_video(
                    previous_video_path=previous_clip_path,
                    input_video_path=input_video_path,
                    prompt=prompt,
                    duration=min(duration, settings.max_clip_duration),
                    output_path=output_path,
                )

            return {
                "clip_index": clip_index,
                "status": result.get("status", "success"),
                "path": result.get("path", str(output_path)),
                "mode": mode,
                "cost_usd": result.get("cost_usd"),
            }

        except Exception as e:
            last_error = str(e)
            error_lower = last_error.lower()

            if any(kw in error_lower for kw in NON_RETRYABLE_KEYWORDS):
                logger.error(f"[Processor] Clip {clip_index} non-retryable: {last_error}")
                break

            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    f"[Processor] Clip {clip_index} attempt {attempt}/{MAX_RETRIES} "
                    f"failed: {last_error}. Retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)

    logger.error(f"[Processor] Clip {clip_index} failed after {MAX_RETRIES} attempts: {last_error}")
    return {
        "clip_index": clip_index,
        "status": "failed",
        "path": input_video_path,
        "mode": mode,
        "error": last_error,
    }


def _build_animate_prompt(user_prompt: str, platform_name: str, clip_index: int, total: int) -> str:
    """Build the prompt for the first clip (animate mode) — beginner-friendly tutorial style."""
    return (
        f"You are creating a professional, beginner-friendly tutorial video.\n\n"
        f"EXACT VISUAL EDIT of this real screen recording from {platform_name}.\n"
        f"- Keep EVERY UI element, text, button, icon, color, layout, font, and data "
        f"100% IDENTICAL to the original video. No changes allowed to the interface.\n"
        f"- Only improve: mouse cursor, motion smoothness, and add voice-over narration.\n\n"
        f"STYLE REQUIREMENTS:\n"
        f"- Friendly, clear, patient tutor voice (warm and encouraging tone)\n"
        f'- Speak naturally like a real teacher: "Now click on the New button here...", '
        f'"Next, let\'s fill in the First Name field...", "Great! Now select the Contacts tab..."\n'
        f"- Voice-over must perfectly sync with the cursor movements\n"
        f"- Cursor: Realistic white arrow with soft shadow. Move smoothly and naturally. "
        f"Hover for 0.3-0.5 seconds on clickable elements before clicking.\n"
        f'- When voice says "click here" or "select this", the cursor must move there '
        f"and click at the exact same moment.\n"
        f"- Smooth 60fps animation, ultra-sharp, clean modern SaaS tutorial style\n"
        f"- No text overlays, no fake data, no layout changes\n\n"
        f"Current step: {clip_index + 1} of {total}\n"
        f"Context: {user_prompt}\n\n"
        f"Generate this clip with realistic voice-over narration + perfectly synced cursor movements."
    )


def _build_extend_prompt(user_prompt: str, platform_name: str, clip_index: int, total: int) -> str:
    """Build the prompt for extend-video mode (clips 1+).

    Maintains the same beginner-friendly tutorial style with voice-over narration
    while ensuring seamless visual continuity from the previous clip.
    """
    return (
        f"You are creating a professional, beginner-friendly tutorial video.\n\n"
        f"CONTINUE EXACTLY from the last frame of the previous video segment.\n"
        f"This is a seamless continuation of the same {platform_name} screen recording.\n\n"
        f"EXACT VISUAL EDIT:\n"
        f"- Keep EVERY UI element, text, button, icon, color, layout, font, and data "
        f"100% IDENTICAL to the original video. No changes allowed to the interface.\n"
        f"- Only improve: mouse cursor, motion smoothness, and add voice-over narration.\n"
        f"- The first frame of this clip MUST match the last frame of the previous clip exactly.\n\n"
        f"STYLE REQUIREMENTS:\n"
        f"- Friendly, clear, patient tutor voice (warm and encouraging tone)\n"
        f'- Speak naturally like a real teacher: "Now click on the New button here...", '
        f'"Next, let\'s fill in the First Name field...", "Great! Now select the Contacts tab..."\n'
        f"- Voice-over must perfectly sync with the cursor movements\n"
        f"- Cursor: Realistic white arrow with soft shadow. Move smoothly and naturally. "
        f"Hover for 0.3-0.5 seconds on clickable elements before clicking.\n"
        f'- When voice says "click here" or "select this", the cursor must move there '
        f"and click at the exact same moment.\n"
        f"- Smooth 60fps animation, ultra-sharp, clean modern SaaS tutorial style\n"
        f"- No text overlays, no fake data, no layout changes\n\n"
        f"Current step: {clip_index + 1} of {total}\n"
        f"Context: {user_prompt}\n\n"
        f"CRITICAL: No jumps. No style changes. Seamless continuation with voice-over narration."
    )
