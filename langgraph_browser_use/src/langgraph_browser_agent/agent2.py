# agent2.py — Video Generation Agent (Agent 2)
# Takes Agent1Output + user_query → generates optimized prompts → produces tutorial video

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .llm import analyze_with_llm
from .models import Agent1Output

logger = logging.getLogger(__name__)

# Output directory for generated videos and metadata
GENERATED_VIDEOS_DIR = Path(__file__).resolve().parents[3] / "langgraph_browser_use" / "generated_videos"

# Add video_pipeline to path for imports
VIDEO_PIPELINE_DIR = Path(__file__).resolve().parents[3] / "video_pipeline"
if str(VIDEO_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(VIDEO_PIPELINE_DIR))

def _import_video_pipeline():
    """Import run_pipeline from video_pipeline with proper path isolation."""
    import importlib.util

    workflow_path = VIDEO_PIPELINE_DIR / "graph" / "workflow.py"
    if not workflow_path.exists():
        raise ImportError(
            f"Video pipeline not found at {workflow_path}. "
            f"Ensure video_pipeline/ is in the project root."
        )

    # Temporarily prepend video_pipeline to sys.path for its internal imports
    video_path_str = str(VIDEO_PIPELINE_DIR)
    was_in_path = video_path_str in sys.path
    if not was_in_path:
        sys.path.insert(0, video_path_str)

    try:
        spec = importlib.util.spec_from_file_location(
            "video_pipeline.graph.workflow", str(workflow_path)
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.run_pipeline
    finally:
        if not was_in_path:
            sys.path.remove(video_path_str)


def _set_video_dry_run(value: bool) -> None:
    """Set dry_run on the video pipeline settings."""
    video_path_str = str(VIDEO_PIPELINE_DIR)
    was_in_path = video_path_str in sys.path
    if not was_in_path:
        sys.path.insert(0, video_path_str)
    try:
        import importlib
        config_mod = importlib.import_module("config.settings")
        config_mod.settings.dry_run = value
    finally:
        if not was_in_path and video_path_str in sys.path:
            sys.path.remove(video_path_str)


AGENT2_SYSTEM_PROMPT = """You are a video prompt engineer for Foxio — an AI that creates beginner-friendly tutorial videos for SaaS platforms.

Your job: Take a platform analysis (pages, workflows, narration script) and convert it into a sequence of video generation prompts optimized for text-to-video AI models (like Grok Imagine Video).

## Rules:
1. Each step = one short video clip (4-8 seconds).
2. Prompts must describe VISUAL screen recordings — what the viewer SEES on screen.
3. Use clear, specific language: mention UI elements, button colors, cursor movements, transitions.
4. Keep prompts under 200 words each — concise but visually descriptive.
5. Order steps logically to form a coherent tutorial flow.
6. Include 3-8 steps total (not too few, not too many).
7. Each prompt should start with "Screen recording showing..." for consistency.
8. Mention the platform name and page context in each prompt for visual grounding.

## Output Format (strict JSON):
{
  "video_title": "How to [action] in [Platform]",
  "total_steps": <number>,
  "steps": [
    {
      "step_number": 1,
      "prompt": "Screen recording showing...",
      "duration": 6,
      "aspect_ratio": "16:9",
      "resolution": "480p",
      "narration_hint": "Brief text overlay or voiceover hint for this clip"
    }
  ]
}
"""


def _build_agent2_input(agent1_output: dict, user_query: str) -> str:
    """Build the user message for the LLM from Agent1Output data."""
    context_for_video = agent1_output.get("context_for_video", "")
    platform_name = agent1_output.get("platform_name", "Unknown Platform")
    current_page = agent1_output.get("current_page", {})
    workflows = agent1_output.get("relevant_workflows", [])
    journey = agent1_output.get("overall_user_journey", "")

    pages_summary = []
    for page in agent1_output.get("pages_captured", []):
        pages_summary.append({
            "title": page.get("title", ""),
            "url": page.get("url", ""),
            "screenshot_path": page.get("screenshot_path", ""),
        })

    return (
        f"## User Query\n\"{user_query}\"\n\n"
        f"## Platform\n{platform_name}\n\n"
        f"## Current Page\n"
        f"Title: {current_page.get('title', '')}\n"
        f"Description: {current_page.get('description', '')}\n"
        f"Main Actions: {json.dumps(current_page.get('main_actions', []))}\n\n"
        f"## User Journey\n{journey}\n\n"
        f"## Workflows\n{json.dumps(workflows, default=str)}\n\n"
        f"## Narration Script (from Agent 1)\n{context_for_video}\n\n"
        f"## Pages Captured\n{json.dumps(pages_summary, default=str)}\n\n"
        f"## Instructions\n"
        f"Convert the above into a sequence of video generation prompts.\n"
        f"Each prompt should describe a specific screen recording moment that a "
        f"text-to-video AI can render. Focus on visual clarity and logical flow.\n"
        f"Respond with JSON matching the schema in your system instructions."
    )


async def generate_video_prompts(
    agent1_output: dict,
    user_query: str,
) -> dict[str, Any]:
    """
    Use LLM to transform Agent1Output into structured video generation steps.

    Returns:
        Dict with video_title, total_steps, and steps array.
    """
    user_message = _build_agent2_input(agent1_output, user_query)

    logger.info("Agent 2: Generating video prompts from Agent 1 output...")

    raw = await analyze_with_llm(
        system_prompt=AGENT2_SYSTEM_PROMPT,
        user_message=user_message,
        use_mini=False,
    )

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"Agent 2: Failed to parse LLM response: {e}")
        raise ValueError(f"Agent 2 LLM returned invalid JSON: {e}") from e

    steps = result.get("steps", [])
    if not steps:
        raise ValueError("Agent 2: LLM returned zero video steps.")

    logger.info(
        f"Agent 2: Generated {len(steps)} video prompts | "
        f"Title: {result.get('video_title', 'Untitled')}"
    )

    return result


async def run_agent2(
    agent1_output: dict,
    user_query: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """
    Full Agent 2 pipeline: Agent1Output → LLM prompt engineering → Video generation.

    Args:
        agent1_output: Dict from Agent1Output.model_dump() or equivalent.
        user_query: Original user question.
        dry_run: If True, skip actual API video generation (saves credits).

    Returns:
        Dict with:
          - status: "completed" | "failed"
          - video_title: Generated title
          - video_prompts: The engineered prompts (steps array)
          - pipeline_result: Full video pipeline output (job_id, final_video_path, etc.)
    """
    # Step 1: Generate optimized video prompts via LLM
    prompt_result = await generate_video_prompts(agent1_output, user_query)

    video_title = prompt_result.get("video_title", "Tutorial Video")
    steps = prompt_result.get("steps", [])

    # Step 2: Format steps for the video pipeline
    pipeline_steps = [
        {
            "prompt": step["prompt"],
            "duration": step.get("duration", 6),
            "aspect_ratio": step.get("aspect_ratio", "16:9"),
            "resolution": step.get("resolution", "480p"),
        }
        for step in steps
    ]

    # Step 3: Run the video generation pipeline
    try:
        run_pipeline = _import_video_pipeline()
    except (ImportError, ModuleNotFoundError) as e:
        logger.error(f"Agent 2: Cannot import video pipeline: {e}")
        return {
            "status": "completed_prompts_only",
            "video_title": video_title,
            "video_prompts": steps,
            "pipeline_result": None,
            "error": f"Video pipeline not available: {e}",
        }

    logger.info(
        f"Agent 2: Running video pipeline | "
        f"{len(pipeline_steps)} clips | dry_run={dry_run}"
    )

    # Override dry_run in settings
    _set_video_dry_run(dry_run)

    pipeline_result = await run_pipeline(
        steps=pipeline_steps,
        model_name=None,
    )

    # Step 4: Save metadata for future analysis
    job_id = pipeline_result.get("job_id", "unknown")
    _save_run_metadata(
        job_id=job_id,
        video_title=video_title,
        user_query=user_query,
        prompts=steps,
        pipeline_result=pipeline_result,
        dry_run=dry_run,
    )

    final_status = pipeline_result.get("status", "unknown")
    logger.info(f"Agent 2: Pipeline finished | status={final_status}")

    return {
        "status": final_status,
        "video_title": video_title,
        "video_prompts": steps,
        "pipeline_result": pipeline_result,
        "metadata_path": str(GENERATED_VIDEOS_DIR / f"{job_id}_metadata.json"),
    }


def _save_run_metadata(
    job_id: str,
    video_title: str,
    user_query: str,
    prompts: list[dict],
    pipeline_result: dict,
    dry_run: bool,
) -> None:
    """Save run metadata as JSON for future analysis."""
    GENERATED_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

    metadata = {
        "job_id": job_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "video_title": video_title,
        "user_query": user_query,
        "dry_run": dry_run,
        "total_clips": len(prompts),
        "prompts": prompts,
        "pipeline_status": pipeline_result.get("status"),
        "final_video_path": pipeline_result.get("final_video_path"),
        "clip_results": pipeline_result.get("clip_results", []),
    }

    metadata_path = GENERATED_VIDEOS_DIR / f"{job_id}_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, default=str))
    logger.info(f"Agent 2: Metadata saved → {metadata_path}")
