"""
Step Splitter — Converts browser agent video_clips into edit-video pipeline steps.

Single responsibility: map raw video_clips from the browser agent into
the format expected by generate_all_clips().
"""

from typing import Any

from loguru import logger

from config.settings import settings

# Duration constants
DEFAULT_DURATION = 4
COMPLEX_ACTION_DURATION = 5
SIMPLE_ACTION_DURATION = 3

# Keywords for duration estimation
COMPLEX_KEYWORDS = {
    "fill", "type", "enter", "select", "choose", "configure",
    "drag", "upload", "search", "scroll", "navigate", "switch",
}

SIMPLE_KEYWORDS = {
    "click", "tap", "press", "hover", "see", "notice", "observe",
    "appear", "display", "show", "open", "close",
}


def split_video_clips_to_steps(
    video_clips: list[dict[str, Any]],
    platform_name: str = "Salesforce",
) -> list[dict[str, Any]]:
    """
    Convert browser agent video_clips into edit-video pipeline steps.

    Args:
        video_clips: List of dicts with keys: step, video_path, narration, action.
        platform_name: Platform name for prompt context.

    Returns:
        List of step dicts ready for generate_all_clips().
    """
    if not video_clips:
        logger.warning("[StepSplitter] No video_clips provided.")
        return []

    steps = []
    for clip in video_clips:
        step_num = clip.get("step", len(steps) + 1)
        video_path = clip.get("video_path", "")
        narration = clip.get("narration", "")
        action = clip.get("action", "")

        if not video_path:
            logger.warning(f"[StepSplitter] Step {step_num} has no video_path — skipping.")
            continue

        duration = _estimate_duration(narration or action)

        steps.append({
            "step": step_num,
            "video_path": video_path,
            "narration": narration,
            "action": action,
            "duration": duration,
            "_platform_name": platform_name,
        })

    logger.info(
        f"[StepSplitter] Converted {len(steps)} video_clips to pipeline steps | "
        f"platform={platform_name}"
    )

    return steps


def _estimate_duration(text: str) -> int:
    """Estimate clip duration — biased SHORT (3-5s)."""
    text_lower = text.lower()

    if any(kw in text_lower for kw in COMPLEX_KEYWORDS):
        return COMPLEX_ACTION_DURATION
    elif any(kw in text_lower for kw in SIMPLE_KEYWORDS):
        return SIMPLE_ACTION_DURATION

    return DEFAULT_DURATION
