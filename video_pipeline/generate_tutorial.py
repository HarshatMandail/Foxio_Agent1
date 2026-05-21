"""
Tutorial Video Generator — Single entry point for Agent 1 → Agent 2 integration.

Usage:
    from generate_tutorial import generate_tutorial_video

    result = await generate_tutorial_video(
        agent1_output=agent1_output_dict,
        user_query="How do I create a new contract?",
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
from nodes.step_splitter import split_agent1_output_to_steps


async def generate_tutorial_video(
    agent1_output: dict[str, Any],
    user_query: str,
    dry_run: bool | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """
    End-to-end tutorial video generation from Agent 1 output.

    Flow:
      1. Split Agent1Output.context_for_video → structured video steps
      2. Run LangGraph video pipeline (generate clips → concatenate → finalize)
      3. Save metadata JSON alongside the video
      4. Return result with video path

    Args:
        agent1_output: Dict from Agent1Output.model_dump() — must contain
                       context_for_video, platform_name, pages_captured, etc.
        user_query: Original user question (e.g., "How do I create a contract?").
        dry_run: Override dry_run setting. None = use .env value.
        job_id: Optional custom job ID for tracking.

    Returns:
        Dict with:
          - status: "completed" | "failed"
          - job_id: Unique job identifier
          - video_title: Generated title
          - final_video_path: Path to the final .mp4 (or "dry_run_no_output")
          - metadata_path: Path to the saved metadata JSON
          - steps_generated: Number of video clips
          - steps: The structured steps used for generation
          - error: Error message if failed
    """
    resolved_job_id = job_id or str(uuid.uuid4())[:8]
    platform_name = agent1_output.get("platform_name", "Unknown")
    use_dry_run = dry_run if dry_run is not None else settings.dry_run

    logger.info("=" * 60)
    logger.info(f"[Job {resolved_job_id}] TUTORIAL VIDEO GENERATION")
    logger.info(f"Platform: {platform_name}")
    logger.info(f"Query: {user_query}")
    logger.info(f"Dry Run: {use_dry_run}")
    logger.info("=" * 60)

    # Step 1: Convert Agent1Output → structured video steps
    try:
        steps = split_agent1_output_to_steps(agent1_output, user_query)
    except Exception as e:
        logger.error(f"[Job {resolved_job_id}] Step splitting failed: {e}")
        return _error_result(resolved_job_id, f"Step splitting failed: {e}")

    if not steps:
        return _error_result(resolved_job_id, "No video steps generated from Agent 1 output.")

    logger.info(f"[Job {resolved_job_id}] Generated {len(steps)} video steps")

    # Step 2: Override dry_run if specified
    original_dry_run = settings.dry_run
    if dry_run is not None:
        settings.dry_run = dry_run

    # Step 3: Run the video generation pipeline
    try:
        pipeline_result = await run_pipeline(
            steps=steps,
            model_name=settings.default_model,
            job_id=resolved_job_id,
        )
    except Exception as e:
        logger.error(f"[Job {resolved_job_id}] Pipeline execution failed: {e}")
        settings.dry_run = original_dry_run
        return _error_result(resolved_job_id, f"Pipeline failed: {e}")
    finally:
        settings.dry_run = original_dry_run

    # Step 4: Build result
    final_status = pipeline_result.get("status", "unknown")
    final_video_path = pipeline_result.get("final_video_path", "")
    video_title = _generate_title(user_query, platform_name)

    # Step 5: Save metadata
    metadata_path = _save_metadata(
        job_id=resolved_job_id,
        video_title=video_title,
        user_query=user_query,
        platform_name=platform_name,
        steps=steps,
        pipeline_result=pipeline_result,
        dry_run=use_dry_run,
    )

    logger.info("=" * 60)
    logger.info(f"[Job {resolved_job_id}] COMPLETE | status={final_status}")
    logger.info(f"[Job {resolved_job_id}] Video: {final_video_path}")
    logger.info(f"[Job {resolved_job_id}] Metadata: {metadata_path}")
    logger.info("=" * 60)

    return {
        "status": final_status,
        "job_id": resolved_job_id,
        "video_title": video_title,
        "final_video_path": final_video_path,
        "metadata_path": str(metadata_path),
        "steps_generated": len(steps),
        "steps": steps,
        "clip_results": pipeline_result.get("clip_results", []),
        "error": pipeline_result.get("error", ""),
    }


def _generate_title(user_query: str, platform_name: str) -> str:
    """Generate a video title from the user query."""
    query_clean = user_query.strip().rstrip("?").strip()

    # Avoid duplication if platform name is already in the query
    platform_lower = platform_name.lower()
    if platform_lower in query_clean.lower():
        if query_clean.lower().startswith("how"):
            return query_clean
        return f"How to {query_clean}"

    if query_clean.lower().startswith("how"):
        return f"{query_clean} in {platform_name}"

    return f"How to {query_clean} in {platform_name}"


def _save_metadata(
    job_id: str,
    video_title: str,
    user_query: str,
    platform_name: str,
    steps: list[dict],
    pipeline_result: dict,
    dry_run: bool,
) -> Path:
    """Save run metadata as JSON for future analysis."""
    settings.final_output_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = settings.final_output_dir / f"{job_id}_metadata.json"

    metadata = {
        "job_id": job_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "video_title": video_title,
        "user_query": user_query,
        "platform_name": platform_name,
        "dry_run": dry_run,
        "total_clips": len(steps),
        "steps": steps,
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
        "steps_generated": 0,
        "steps": [],
        "clip_results": [],
        "error": error,
    }
