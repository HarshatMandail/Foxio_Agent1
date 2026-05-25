"""
Video Generation Pipeline — Main Entry Point

Demonstrates the Edit-Video pipeline with sample video clips.
In production, video_clips come from Agent 1's browser recordings.

Usage:
    python main.py              # Run with sample video clips (dry-run)
    python main.py --help       # Show usage
"""

import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

from loguru import logger

from config.settings import settings
from generate_tutorial import generate_tutorial_video

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


def _create_sample_video_clips() -> list[dict]:
    """Create sample .webm files to demonstrate the pipeline.

    In production, these come from Agent 1's Playwright browser recordings.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="sample_clips_"))

    sample_steps = [
        {"narration": "Click the Contacts tab in the navigation bar", "action": "click_nav: Contacts"},
        {"narration": "Click the New button to open the contact form", "action": "click_button: New"},
        {"narration": "Fill in the First Name field", "action": "type: First Name"},
    ]

    clips = []
    for i, step_data in enumerate(sample_steps, start=1):
        video_path = tmp_dir / f"step_{i:02d}_sample.webm"

        # Generate a short test video using FFmpeg
        try:
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c=0x1a1a2e:s=1280x720:d=4",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-t", "4",
                "-c:v", "libvpx", "-c:a", "libvorbis",
                str(video_path),
            ]
            subprocess.run(cmd, capture_output=True, timeout=30, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback: create a minimal dummy file for dry-run testing
            video_path.write_bytes(b"\x1a\x45\xdf\xa3" * 256)

        clips.append({
            "step": i,
            "video_path": str(video_path),
            "narration": step_data["narration"],
            "action": step_data["action"],
        })

    return clips


async def main() -> None:
    """Run the Edit-Video pipeline with sample data."""
    logger.info("=" * 60)
    logger.info("VIDEO PIPELINE — Edit-Video Mode")
    logger.info(f"Model: {settings.default_model}")
    logger.info(f"Dry Run: {settings.dry_run}")
    logger.info("=" * 60)

    # Create sample video clips (simulating Agent 1 output)
    video_clips = _create_sample_video_clips()

    logger.info(f"Sample clips created: {len(video_clips)}")
    for clip in video_clips:
        logger.info(f"  Step {clip['step']}: {clip['narration']}")

    # Run the tutorial video generation
    result = await generate_tutorial_video(
        video_clips=video_clips,
        platform_name="Salesforce",
        user_query="How do I create a new contact in Salesforce?",
    )

    # Print results
    logger.info("=" * 60)
    logger.info("RESULT")
    logger.info("=" * 60)
    logger.info(f"Status: {result.get('status')}")
    logger.info(f"Job ID: {result.get('job_id')}")
    logger.info(f"Title: {result.get('video_title')}")
    logger.info(f"Clips: {result.get('clips_processed')}")

    final_path = result.get("final_video_path", "")
    if final_path and final_path != "dry_run_no_output":
        logger.success(f"Video: {final_path}")
    elif final_path == "dry_run_no_output":
        logger.info("Video: dry_run (no file generated)")

    if result.get("metadata_path"):
        logger.info(f"Metadata: {result['metadata_path']}")

    if result.get("error"):
        logger.error(f"Error: {result['error']}")

    clip_results = result.get("clip_results", [])
    if clip_results:
        success = sum(1 for c in clip_results if c.get("status") in ("success", "dry_run"))
        failed = sum(1 for c in clip_results if c.get("status") == "failed")
        logger.info(f"Clip results: {success} success, {failed} failed")


if __name__ == "__main__":
    asyncio.run(main())
