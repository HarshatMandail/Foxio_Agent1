"""
Tutorial Video Generator — Entry point for Agent 1 → Edit-Video pipeline.

Takes video_clips from Agent 1's browser recordings and produces a polished
tutorial video using Grok Imagine Video's edit-video mode.

Usage:
    from generate_tutorial import generate_tutorial_video

    result = await generate_tutorial_video(
        video_clips=agent1_output.video_clips,
        platform_name="Salesforce",
        user_query="How do I create a new contact?",
    )
    print(result["final_video_path"])
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from config.settings import settings
from graph.workflow import run_pipeline


async def generate_tutorial_video(
    video_clips: list[dict[str, Any]],
    platform_name: str = "Salesforce",
    user_query: str = "",
    job_id: str | None = None,
) -> dict[str, Any]:
    """
    Generate a polished tutorial video from real browser recordings.

    Flow:
      1. Validate video_clips from Agent 1
      2. Run Edit-Video pipeline (preprocess → enhance → concatenate → finalize)
      3. Save metadata JSON alongside the video
      4. Return result with video path

    Args:
        video_clips: List of dicts from Agent 1 with keys:
            step, video_path, narration, action.
        platform_name: Platform name for prompt context.
        user_query: Original user question.
        job_id: Optional custom job ID for tracking.

    Returns:
        Dict with status, job_id, video_title, final_video_path, metadata_path, error.
    """
    resolved_job_id = job_id or str(uuid.uuid4())[:8]
    video_title = _generate_title(user_query, platform_name)

    logger.info("=" * 60)
    logger.info(f"[Job {resolved_job_id}] TUTORIAL VIDEO GENERATION")
    logger.info(f"Platform: {platform_name}")
    logger.info(f"Query: {user_query}")
    logger.info(f"Video clips: {len(video_clips)}")
    logger.info("=" * 60)

    if not video_clips:
        return _error_result(resolved_job_id, "No video clips provided by Agent 1.")

    valid_clips = [c for c in video_clips if c.get("video_path")]
    if not valid_clips:
        return _error_result(resolved_job_id, "No video clips with valid video_path found.")

    # Inject platform name into clips for prompt building
    for clip in valid_clips:
        clip.setdefault("_platform_name", platform_name)

    # Run the Edit-Video pipeline
    try:
        pipeline_result = await run_pipeline(
            video_clips=valid_clips,
            job_id=resolved_job_id,
        )
    except Exception as e:
        logger.error(f"[Job {resolved_job_id}] Pipeline execution failed: {e}")
        return _error_result(resolved_job_id, f"Pipeline failed: {e}")

    # Build result
    final_status = pipeline_result.get("status", "unknown")
    final_video_path = pipeline_result.get("final_video_path", "")

    # Save metadata
    metadata_path = _save_metadata(
        job_id=resolved_job_id,
        video_title=video_title,
        user_query=user_query,
        platform_name=platform_name,
        video_clips=valid_clips,
        pipeline_result=pipeline_result,
    )

    logger.info("=" * 60)
    logger.info(f"[Job {resolved_job_id}] COMPLETE | status={final_status}")
    logger.info(f"[Job {resolved_job_id}] Video: {final_video_path}")
    logger.info("=" * 60)

    return {
        "status": final_status,
        "job_id": resolved_job_id,
        "video_title": video_title,
        "final_video_path": final_video_path,
        "metadata_path": str(metadata_path),
        "clips_processed": len(valid_clips),
        "clip_results": pipeline_result.get("clip_results", []),
        "error": pipeline_result.get("error", ""),
    }


def _generate_title(user_query: str, platform_name: str) -> str:
    """Generate a video title from the user query."""
    if not user_query:
        return f"{platform_name} Tutorial"

    query_clean = user_query.strip().rstrip("?").strip()

    if platform_name.lower() in query_clean.lower():
        return query_clean if query_clean.lower().startswith("how") else f"How to {query_clean}"

    if query_clean.lower().startswith("how"):
        return f"{query_clean} in {platform_name}"

    return f"How to {query_clean} in {platform_name}"


def _save_metadata(
    job_id: str,
    video_title: str,
    user_query: str,
    platform_name: str,
    video_clips: list[dict],
    pipeline_result: dict,
) -> Path:
    """Save run metadata as JSON."""
    settings.final_output_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = settings.final_output_dir / f"{job_id}_metadata.json"

    metadata = {
        "job_id": job_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "video_title": video_title,
        "user_query": user_query,
        "platform_name": platform_name,
        "total_clips": len(video_clips),
        "video_clips": video_clips,
        "pipeline_status": pipeline_result.get("status"),
        "final_video_path": pipeline_result.get("final_video_path"),
        "clip_results": pipeline_result.get("clip_results", []),
    }

    metadata_path.write_text(json.dumps(metadata, indent=2, default=str))
    logger.info(f"[Job {job_id}] Metadata saved -> {metadata_path}")
    return metadata_path


def _error_result(job_id: str, error: str) -> dict[str, Any]:
    """Build a standardized error result."""
    return {
        "status": "failed",
        "job_id": job_id,
        "video_title": "",
        "final_video_path": "",
        "metadata_path": "",
        "clips_processed": 0,
        "clip_results": [],
        "error": error,
    }
