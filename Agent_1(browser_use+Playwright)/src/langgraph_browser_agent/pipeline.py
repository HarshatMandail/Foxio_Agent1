# pipeline.py — Unified Foxio Pipeline: Agent 1 (Browser + Video Recording) → Agent 2 (Edit-Video)

import logging
import sys
from pathlib import Path
from typing import Any

from .agent import run_agent1
from .models import Agent1Output

logger = logging.getLogger(__name__)

# Add video_pipeline to path for imports
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
      Agent 1: Navigate platform → capture pages → record video clips → analyze with LLM
      Agent 2: Preprocess clips → enhance with Edit-Video → concatenate → final tutorial

    Args:
        url: Platform URL to analyze.
        user_query: User's question (e.g., "How do I create a contact?").
        cleanup_browser: If True, close browser after Agent 1 finishes.

    Returns:
        Dict with agent1_output, video generation result, and overall status.
    """
    logger.info("=" * 60)
    logger.info("FOXIO PIPELINE — Agent 1 → Edit-Video")
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
        return {
            "status": "failed",
            "stage": "agent1",
            "error": str(e),
            "agent1_output": None,
            "video_result": None,
        }

    logger.info(
        f"[Pipeline] Agent 1 complete | "
        f"Platform: {agent1_output.platform_name} | "
        f"Pages: {len(agent1_output.pages_captured)} | "
        f"Video clips: {len(agent1_output.video_clips)}"
    )

    # ─── Agent 2: Edit-Video Pipeline ─────────────────────────────────────────
    video_clips = agent1_output.video_clips

    if not video_clips:
        logger.warning("[Pipeline] No video clips recorded. Cannot generate tutorial video.")
        return {
            "status": "partial",
            "stage": "no_video_clips",
            "error": "Agent 1 completed but recorded no video clips.",
            "agent1_output": agent1_output.model_dump(),
            "video_result": None,
        }

    logger.info(f"[Pipeline] Running Agent 2: Edit-Video pipeline ({len(video_clips)} clips)...")

    try:
        generate_tutorial_video = _import_generate_tutorial()
    except (ImportError, ModuleNotFoundError) as e:
        logger.error(f"[Pipeline] Cannot import video pipeline: {e}")
        return {
            "status": "partial",
            "stage": "import_failed",
            "error": f"Video pipeline not available: {e}",
            "agent1_output": agent1_output.model_dump(),
            "video_result": None,
        }

    try:
        video_result = await generate_tutorial_video(
            video_clips=video_clips,
            platform_name=agent1_output.platform_name,
            user_query=user_query,
        )
    except Exception as e:
        logger.error(f"[Pipeline] Video generation failed: {e}")
        return {
            "status": "partial",
            "stage": "video_failed",
            "error": str(e),
            "agent1_output": agent1_output.model_dump(),
            "video_result": None,
        }

    logger.info(
        f"[Pipeline] Video generation complete | "
        f"Status: {video_result.get('status')} | "
        f"Video: {video_result.get('final_video_path', 'N/A')}"
    )

    # ─── Final Result ─────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("[Pipeline] FULL PIPELINE COMPLETE")
    logger.info("=" * 60)

    return {
        "status": "completed",
        "stage": "done",
        "agent1_output": agent1_output.model_dump(),
        "video_result": video_result,
    }
