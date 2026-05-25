# pipeline.py — Unified Foxio Pipeline: Agent 1 (Browser + Merge) → Agent 2 (Split + Animate + Extend)

import logging
import sys
from pathlib import Path
from typing import Any

from .agent import run_agent1
from .models import Agent1Output
from .video_merger import merge_all_recordings

logger = logging.getLogger(__name__)

_VIDEO_PIPELINE_DIR = Path(__file__).resolve().parents[3] / "Agent_2(AI_Video_Generation)"


def _import_generate_tutorial():
    """Import generate_tutorial_video from the video pipeline."""
    video_path_str = str(_VIDEO_PIPELINE_DIR)
    if video_path_str not in sys.path:
        sys.path.insert(0, video_path_str)
    from generate_tutorial import generate_tutorial_video
    return generate_tutorial_video


async def run_full_pipeline(
    url: str,
    user_query: str,
    cleanup_browser: bool = False,
) -> dict[str, Any]:
    """
    Execute the complete Foxio pipeline:
      Agent 1: Navigate → record videos (multiple tabs/pages) → merge into ONE raw .mp4
      Agent 2: Split into ≤8s clips → animate first → extend rest → concat final video

    Args:
        url: Platform URL to analyze.
        user_query: User's question.
        cleanup_browser: If True, close browser after Agent 1 finishes.

    Returns:
        Dict with agent1_output, video generation result, and overall status.
    """
    logger.info("=" * 60)
    logger.info("FOXIO PIPELINE — Record → Merge → Split → Animate → Extend")
    logger.info(f"URL: {url}")
    logger.info(f"Query: {user_query}")
    logger.info("=" * 60)

    # ─── Agent 1: Browser Navigation + Video Recording ────────────────────────
    logger.info("[Pipeline] Running Agent 1: Platform analysis + video recording...")

    try:
        agent1_output: Agent1Output = await run_agent1(
            url=url,
            user_query=user_query,
            cleanup_browser=cleanup_browser,
        )
    except Exception as e:
        logger.error(f"[Pipeline] Agent 1 failed: {e}")
        return {"status": "failed", "stage": "agent1", "error": str(e)}

    logger.info(
        f"[Pipeline] Agent 1 complete | "
        f"Platform: {agent1_output.platform_name} | "
        f"Pages: {len(agent1_output.pages_captured)} | "
        f"Video clips: {len(agent1_output.video_clips)}"
    )

    # ─── Merge all recordings into ONE raw .mp4 ──────────────────────────────
    logger.info("[Pipeline] Merging all recorded videos into single raw .mp4...")

    try:
        raw_video_path = merge_all_recordings(output_filename="raw_recording.mp4")
    except RuntimeError as e:
        logger.error(f"[Pipeline] Video merge failed: {e}")
        return {
            "status": "partial",
            "stage": "merge_failed",
            "error": str(e),
            "agent1_output": agent1_output.model_dump(),
        }

    if not raw_video_path:
        logger.warning("[Pipeline] No recordings to merge. Cannot generate video.")
        return {
            "status": "partial",
            "stage": "no_recordings",
            "error": "No video recordings found after browser task.",
            "agent1_output": agent1_output.model_dump(),
        }

    logger.info(f"[Pipeline] Merged raw video: {raw_video_path}")

    # ─── Agent 2: Split → Animate → Extend → Concat ──────────────────────────
    logger.info("[Pipeline] Running Agent 2: Split + Animate + Extend pipeline...")

    try:
        generate_tutorial_video = _import_generate_tutorial()
    except (ImportError, ModuleNotFoundError) as e:
        logger.error(f"[Pipeline] Cannot import video pipeline: {e}")
        return {
            "status": "partial",
            "stage": "import_failed",
            "error": str(e),
            "agent1_output": agent1_output.model_dump(),
            "raw_video_path": raw_video_path,
        }

    user_prompt = (
        f"Professional SaaS tutorial for {agent1_output.platform_name}. "
        f"Smooth realistic cursor, clean 60fps motion, ultra sharp. "
        f"Task: {user_query}"
    )

    try:
        video_result = await generate_tutorial_video(
            raw_video_path=raw_video_path,
            user_prompt=user_prompt,
            platform_name=agent1_output.platform_name,
        )
    except Exception as e:
        logger.error(f"[Pipeline] Video generation failed: {e}")
        return {
            "status": "partial",
            "stage": "video_failed",
            "error": str(e),
            "agent1_output": agent1_output.model_dump(),
            "raw_video_path": raw_video_path,
        }

    logger.info(
        f"[Pipeline] Video generation complete | "
        f"Status: {video_result.get('status')} | "
        f"Video: {video_result.get('final_video_path', 'N/A')}"
    )

    logger.info("=" * 60)
    logger.info("[Pipeline] FULL PIPELINE COMPLETE")
    logger.info("=" * 60)

    return {
        "status": "completed",
        "stage": "done",
        "agent1_output": agent1_output.model_dump(),
        "raw_video_path": raw_video_path,
        "video_result": video_result,
    }
