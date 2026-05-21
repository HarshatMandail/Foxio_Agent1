"""
LangGraph StateGraph workflow for the video generation pipeline.

Nodes:
  1. enqueue_clips — Validate and prepare for generation
  2. generate_all_clips — Generate all clips (async, graceful failure)
  3. concatenate_clips — Merge successful clips into final video
  4. finalize — Cleanup and return metadata
"""

import asyncio
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from loguru import logger
from pydantic import BaseModel

from config.settings import settings
from nodes.utils import cleanup_clips, concatenate_clips, ensure_directories
from nodes.video_generator import generate_clip


# --- State Schema ---


class TutorialStep(BaseModel):
    """A single tutorial step provided by Agent 1."""

    prompt: str
    duration: int = 6
    aspect_ratio: str = "16:9"
    resolution: str = "480p"
    start_image: str | None = None  # Local screenshot path or URL for image-to-video


class PipelineState(TypedDict):
    """State passed between LangGraph nodes."""

    job_id: str
    steps: list[dict[str, Any]]
    model_name: str
    clip_results: list[dict[str, Any]]
    final_video_path: str
    status: str
    error: str


# --- Node Functions ---


def node_enqueue_clips(state: PipelineState) -> dict[str, Any]:
    """Node 1: Validate steps and prepare for generation."""
    job_id = state.get("job_id") or str(uuid.uuid4())[:8]
    ensure_directories()

    steps = state["steps"]
    model_name = state.get("model_name") or settings.default_model

    logger.info(
        f"[Job {job_id}] Pipeline started | "
        f"{len(steps)} steps | model={model_name}"
    )

    return {
        "job_id": job_id,
        "model_name": model_name,
        "status": "generating",
    }


def node_generate_all_clips(state: PipelineState) -> dict[str, Any]:
    """Node 2: Generate all video clips concurrently."""
    steps = state["steps"]
    model_name = state["model_name"]
    job_id = state["job_id"]

    logger.info(f"[Job {job_id}] Generating {len(steps)} clips...")

    async def _run_all() -> list[dict[str, Any]]:
        tasks = [
            generate_clip(
                step_index=i,
                prompt=step["prompt"],
                model_name=model_name,
                duration=step.get("duration", 6),
                aspect_ratio=step.get("aspect_ratio", "16:9"),
                resolution=step.get("resolution", "480p"),
                start_image=step.get("start_image"),
            )
            for i, step in enumerate(steps)
        ]
        return list(await asyncio.gather(*tasks))

    # Run async clips in a separate thread to avoid nested event loop error
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, _run_all())
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
    clip_results = state["clip_results"]

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

    logger.success(
        f"[Job {job_id}] Pipeline complete | "
        f"final_video={state['final_video_path']}"
    )

    return {"status": "completed", "error": ""}


# --- Graph Builder ---


def build_pipeline_graph() -> StateGraph:
    """Build and compile the LangGraph video generation pipeline."""
    graph = StateGraph(PipelineState)

    graph.add_node("enqueue_clips", node_enqueue_clips)
    graph.add_node("generate_all_clips", node_generate_all_clips)
    graph.add_node("concatenate_clips", node_concatenate)
    graph.add_node("finalize", node_finalize)

    graph.set_entry_point("enqueue_clips")
    graph.add_edge("enqueue_clips", "generate_all_clips")
    graph.add_edge("generate_all_clips", "concatenate_clips")
    graph.add_edge("concatenate_clips", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


async def run_pipeline(
    steps: list[dict[str, Any]],
    model_name: str | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """
    Execute the full video generation pipeline.

    Args:
        steps: List of tutorial steps from Agent 1.
        model_name: Override the default model.
        job_id: Optional custom job ID for tracking.

    Returns:
        Final pipeline state with video path and metadata.
    """
    validated_steps = [TutorialStep(**step).model_dump() for step in steps]

    initial_state: PipelineState = {
        "job_id": job_id or str(uuid.uuid4())[:8],
        "steps": validated_steps,
        "model_name": model_name or settings.default_model,
        "clip_results": [],
        "final_video_path": "",
        "status": "pending",
        "error": "",
    }

    pipeline = build_pipeline_graph()
    final_state = pipeline.invoke(initial_state)

    return final_state
