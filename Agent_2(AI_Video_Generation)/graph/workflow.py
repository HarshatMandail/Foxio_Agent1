"""
LangGraph StateGraph workflow for the video generation pipeline.

Edit-Video only — linear pipeline with no routing.

Nodes:
  1. enqueue_clips — Validate inputs and prepare for generation
  2. generate_clips — Enhance all clips using edit-video mode
  3. concatenate_clips — Merge successful clips into final video
  4. finalize — Cleanup temp files and return metadata
"""

import asyncio
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from loguru import logger

from config.settings import settings
from nodes.utils import cleanup_clips, cleanup_preprocessed, concatenate_clips, ensure_directories
from nodes.video_generator import generate_all_clips


# --- State Schema ---


class PipelineState(TypedDict):
    """State passed between LangGraph nodes."""

    job_id: str
    video_clips: list[dict[str, Any]]
    clip_results: list[dict[str, Any]]
    final_video_path: str
    status: str
    error: str


# --- Node Functions ---


def node_enqueue_clips(state: PipelineState) -> dict[str, Any]:
    """Node 1: Validate video clips and prepare for generation."""
    job_id = state.get("job_id") or str(uuid.uuid4())[:8]
    ensure_directories()

    video_clips = state.get("video_clips", [])
    valid_clips = [c for c in video_clips if c.get("video_path")]

    logger.info(
        f"[Job {job_id}] Pipeline started | "
        f"{len(valid_clips)} video clips to process"
    )

    if not valid_clips:
        logger.error(f"[Job {job_id}] No valid video clips provided.")
        return {
            "job_id": job_id,
            "status": "failed",
            "error": "No valid video clips provided. Each clip must have a video_path.",
        }

    return {
        "job_id": job_id,
        "video_clips": valid_clips,
        "status": "generating",
    }


def node_generate_clips(state: PipelineState) -> dict[str, Any]:
    """Node 2: Generate all enhanced clips using edit-video mode."""
    video_clips = state.get("video_clips", [])
    job_id = state["job_id"]

    if state.get("status") == "failed":
        return {"clip_results": [], "status": "failed"}

    logger.info(f"[Job {job_id}] Generating {len(video_clips)} clips with Edit-Video mode...")

    async def _run() -> list[dict[str, Any]]:
        return await generate_all_clips(video_clips=video_clips)

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, _run())
        clip_results = future.result()

    successful = [r for r in clip_results if r["status"] in ("success", "dry_run")]
    failed = [r for r in clip_results if r["status"] == "failed"]

    logger.info(
        f"[Job {job_id}] Generation complete | "
        f"success={len(successful)} | failed={len(failed)}"
    )

    return {"clip_results": clip_results, "status": "concatenating"}


def node_concatenate(state: PipelineState) -> dict[str, Any]:
    """Node 3: Concatenate all successful clips into one final video."""
    job_id = state["job_id"]
    clip_results = state.get("clip_results", [])

    if state.get("status") == "failed":
        return {"final_video_path": "", "status": "failed"}

    # In dry_run mode, skip concatenation (no real files exist)
    if any(r["status"] == "dry_run" for r in clip_results):
        logger.info(f"[Job {job_id}] Dry run — skipping concatenation.")
        return {"final_video_path": "dry_run_no_output", "status": "finalizing"}

    successful_paths = [
        r["path"]
        for r in sorted(clip_results, key=lambda x: x["step_index"])
        if r["status"] == "success"
    ]

    if not successful_paths:
        logger.error(f"[Job {job_id}] No successful clips to concatenate.")
        return {
            "status": "failed",
            "error": "All clip generations failed. No video produced.",
            "final_video_path": "",
        }

    try:
        final_path = concatenate_clips(successful_paths, job_id)
        return {"final_video_path": str(final_path), "status": "finalizing"}
    except RuntimeError as e:
        logger.error(f"[Job {job_id}] Concatenation failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "final_video_path": "",
        }


def node_finalize(state: PipelineState) -> dict[str, Any]:
    """Node 4: Cleanup temp files and return final metadata."""
    job_id = state["job_id"]

    cleanup_clips()
    cleanup_preprocessed()

    logger.success(
        f"[Job {job_id}] Pipeline complete | "
        f"final_video={state.get('final_video_path', 'none')}"
    )

    return {"status": "completed", "error": ""}


# --- Graph Builder ---


def build_pipeline_graph() -> StateGraph:
    """Build and compile the LangGraph video generation pipeline.

    Linear graph: enqueue → generate → concatenate → finalize
    """
    graph = StateGraph(PipelineState)

    graph.add_node("enqueue_clips", node_enqueue_clips)
    graph.add_node("generate_clips", node_generate_clips)
    graph.add_node("concatenate_clips", node_concatenate)
    graph.add_node("finalize", node_finalize)

    graph.set_entry_point("enqueue_clips")
    graph.add_edge("enqueue_clips", "generate_clips")
    graph.add_edge("generate_clips", "concatenate_clips")
    graph.add_edge("concatenate_clips", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


async def run_pipeline(
    video_clips: list[dict[str, Any]],
    job_id: str | None = None,
) -> dict[str, Any]:
    """
    Execute the full video generation pipeline.

    Args:
        video_clips: Real browser recordings from Agent 1.
            Each dict must have: step, video_path, narration, action.
        job_id: Optional custom job ID for tracking.

    Returns:
        Final pipeline state with video path and metadata.
    """
    initial_state: PipelineState = {
        "job_id": job_id or str(uuid.uuid4())[:8],
        "video_clips": video_clips or [],
        "clip_results": [],
        "final_video_path": "",
        "status": "pending",
        "error": "",
    }

    pipeline = build_pipeline_graph()
    final_state = pipeline.invoke(initial_state)

    return final_state
