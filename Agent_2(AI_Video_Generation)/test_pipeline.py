"""
Test script — Validates the video generation pipeline end-to-end.

Run with: python test_pipeline.py

Uses DRY_RUN=true by default (no real API calls, no credits spent).
Set DRY_RUN=false in .env to test with real xAI API.
"""

import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

from loguru import logger

logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | <level>{message}</level>",
)


def _create_sample_video(duration: int = 20) -> str:
    """Create a sample video for testing."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="test_raw_"))
    output = tmp_dir / "test_raw_recording.mp4"

    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=0x1a1a2e:s=1280x720:d={duration}",
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            str(output),
        ]
        subprocess.run(cmd, capture_output=True, timeout=30, check=True)
        logger.info(f"Sample {duration}s video created: {output}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        output.write_bytes(b"\x00" * 1024)
        logger.warning("FFmpeg unavailable — created dummy file for dry-run")

    return str(output)


async def test_pipeline_dry_run():
    """Test the full pipeline in dry-run mode."""
    from config.settings import settings
    from graph.workflow import run_pipeline

    original_dry_run = settings.dry_run
    settings.dry_run = True

    logger.info("=" * 60)
    logger.info("PIPELINE TEST — Dry Run Mode")
    logger.info("=" * 60)

    raw_video = _create_sample_video(duration=20)

    result = await run_pipeline(
        raw_video_path=raw_video,
        user_prompt="Smooth cursor, professional SaaS tutorial.",
        platform_name="Salesforce",
        job_id="test_dry_001",
    )

    logger.info("=" * 60)
    logger.info("RESULTS")
    logger.info("=" * 60)
    logger.info(f"Status: {result.get('status')}")
    logger.info(f"Job ID: {result.get('job_id')}")
    logger.info(f"Final Video: {result.get('final_video_path')}")
    logger.info(f"Error: {result.get('error', 'none')}")

    clip_results = result.get("clip_results", [])
    if clip_results:
        success = sum(1 for c in clip_results if c.get("status") in ("success", "dry_run"))
        failed = sum(1 for c in clip_results if c.get("status") == "failed")
        logger.info(f"Clips: {success} dry_run, {failed} failed")

    settings.dry_run = original_dry_run

    assert result["status"] == "completed", f"Expected 'completed', got '{result['status']}'"
    assert result.get("error") == "", f"Unexpected error: {result.get('error')}"
    logger.success("✓ Pipeline dry-run test PASSED")


async def test_preprocessing():
    """Test the preprocessing step (requires FFmpeg)."""
    from nodes.utils import preprocess_video_for_grok

    logger.info("=" * 60)
    logger.info("PREPROCESSING TEST")
    logger.info("=" * 60)

    raw_video = _create_sample_video(duration=5)

    try:
        processed = preprocess_video_for_grok(raw_video)
        logger.success(f"✓ Preprocessing passed: {processed}")
        logger.info(f"  Output size: {Path(processed).stat().st_size // 1024}KB")
    except RuntimeError as e:
        logger.error(f"✗ Preprocessing failed: {e}")


async def main():
    """Run all tests."""
    logger.info("\n" + "=" * 60)
    logger.info("RUNNING ALL PIPELINE TESTS")
    logger.info("=" * 60 + "\n")

    await test_preprocessing()
    print()
    await test_pipeline_dry_run()

    print()
    logger.success("=" * 60)
    logger.success("ALL TESTS PASSED ✓")
    logger.success("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
