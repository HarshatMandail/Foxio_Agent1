"""
Video Generation Pipeline — Main Entry Point

Uses the official xAI SDK (gRPC) for Grok Imagine Video generation.
Demonstrates running the full LangGraph pipeline with sample tutorial steps.

Usage:
    python main.py
"""

import asyncio
import sys

from loguru import logger

from config.settings import settings
from graph.workflow import run_pipeline

# Configure loguru
logger.remove()
logger.add(
    sys.stdout,
    level=settings.log_level,
    format=(
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan> | "
        "<level>{message}</level>"
    ),
)


# Sample tutorial steps (simulating Agent 1 output)
SAMPLE_STEPS = [
    {
        "prompt": (
            "Screen recording showing a user clicking the 'Create Contract' "
            "button on a CLM dashboard. Clean UI, professional SaaS interface."
        ),
        "duration": 6,
        "aspect_ratio": "16:9",
        "resolution": "480p",
    },
    {
        "prompt": (
            "Screen recording showing a contract template selection modal "
            "appearing with multiple template options. User hovers over "
            "'NDA Template' and selects it."
        ),
        "duration": 8,
        "aspect_ratio": "16:9",
        "resolution": "480p",
    },
    {
        "prompt": (
            "Screen recording showing a contract editor with fields being "
            "auto-filled. The user types a company name in the party field. "
            "Professional legal document interface."
        ),
        "duration": 10,
        "aspect_ratio": "16:9",
        "resolution": "480p",
    },
    {
        "prompt": (
            "Screen recording showing the user clicking 'Send for Signature' "
            "button. A success toast notification appears confirming the "
            "contract was sent. Clean, modern UI."
        ),
        "duration": 6,
        "aspect_ratio": "16:9",
        "resolution": "480p",
    },
]


async def main() -> None:
    """Run the video generation pipeline with sample data."""
    logger.info("=" * 60)
    logger.info("VIDEO GENERATION PIPELINE — xAI Official SDK")
    logger.info("=" * 60)
    logger.info(f"Provider: xAI (gRPC via xai-sdk)")
    logger.info(f"Model: {settings.default_model}")
    logger.info(f"Steps: {len(SAMPLE_STEPS)}")
    logger.info(f"Output: {settings.final_output_dir}")
    logger.info("=" * 60)

    result = await run_pipeline(
        steps=SAMPLE_STEPS,
        model_name=settings.default_model,
    )

    logger.info("=" * 60)
    logger.info("PIPELINE RESULT")
    logger.info("=" * 60)
    logger.info(f"Status: {result['status']}")
    logger.info(f"Job ID: {result['job_id']}")

    if result["status"] == "completed":
        logger.success(f"Final Video: {result['final_video_path']}")
        successful = [
            r for r in result["clip_results"]
            if r["status"] in ("success", "dry_run")
        ]
        failed = [
            r for r in result["clip_results"] if r["status"] == "failed"
        ]
        logger.info(f"Clips: {len(successful)} success, {len(failed)} failed")
    else:
        logger.error(f"Error: {result.get('error', 'Unknown')}")


if __name__ == "__main__":
    asyncio.run(main())
