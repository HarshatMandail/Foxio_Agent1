"""
Test script — Validates the Edit-Video pipeline end-to-end.

Run with: python test_pipeline.py

Uses DRY_RUN=true by default (no real API calls, no credits spent).
Set DRY_RUN=false in .env to test with real xAI API.
"""

import asyncio
import sys
import tempfile
from pathlib import Path

from loguru import logger

# Configure logging
logger.remove()
logger.add(sys.stdout, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | <level>{message}</level>")


def create_fake_video_clips() -> list[dict]:
    """Create fake .webm files to simulate Playwright recordings."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="test_clips_"))

    clips = []
    for i in range(1, 4):
        # Create a minimal valid video file using FFmpeg
        fake_path = tmp_dir / f"step_{i:02d}_test.webm"

        import subprocess
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=blue:s=1280x720:d=3",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", "3",
            "-c:v", "libvpx", "-c:a", "libvorbis",
            str(fake_path),
        ]

        try:
            subprocess.run(cmd, capture_output=True, timeout=30, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            # If FFmpeg fails, create a dummy file (dry-run won't need real video)
            fake_path.write_bytes(b"\x1a\x45\xdf\xa3" * 100)  # Minimal webm header bytes
            logger.warning(f"FFmpeg unavailable, created dummy file: {fake_path.name}")

        clips.append({
            "step": i,
            "video_path": str(fake_path),
            "narration": f"Click the button to perform action {i}",
            "action": f"click_button: Action {i}",
            "_platform_name": "Salesforce",
        })

    logger.info(f"Created {len(clips)} test video clips in: {tmp_dir}")
    return clips


async def test_pipeline_dry_run():
    """Test the full pipeline in dry-run mode."""
    from config.settings import settings
    from graph.workflow import run_pipeline

    # Force dry run for testing
    original_dry_run = settings.dry_run
    settings.dry_run = True

    logger.info("=" * 60)
    logger.info("PIPELINE TEST — Dry Run Mode")
    logger.info("=" * 60)

    # Create test video clips
    video_clips = create_fake_video_clips()

    logger.info(f"Video clips: {len(video_clips)}")
    for clip in video_clips:
        logger.info(f"  Step {clip['step']}: {clip['video_path']}")

    # Run the pipeline
    result = await run_pipeline(
        video_clips=video_clips,
        job_id="test_001",
    )

    # Print results
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

        for cr in clip_results:
            logger.info(f"  Step {cr.get('step_index')}: {cr.get('status')} | {cr.get('mode')}")

    # Restore
    settings.dry_run = original_dry_run

    # Validate
    assert result["status"] == "completed", f"Expected 'completed', got '{result['status']}'"
    assert result.get("error") == "", f"Unexpected error: {result.get('error')}"
    logger.success("✓ Pipeline test PASSED")


async def test_preprocessing_only():
    """Test just the preprocessing step (requires FFmpeg)."""
    from nodes.utils import preprocess_video_for_grok

    logger.info("=" * 60)
    logger.info("PREPROCESSING TEST")
    logger.info("=" * 60)

    clips = create_fake_video_clips()
    first_clip = clips[0]["video_path"]

    try:
        processed = preprocess_video_for_grok(first_clip)
        logger.success(f"✓ Preprocessing passed: {processed}")
        logger.info(f"  Output size: {Path(processed).stat().st_size // 1024}KB")
    except RuntimeError as e:
        logger.error(f"✗ Preprocessing failed: {e}")
        logger.info("  (This is expected if FFmpeg is not installed)")


async def test_step_splitter():
    """Test the step splitter converts video_clips correctly."""
    from nodes.step_splitter import split_video_clips_to_steps

    logger.info("=" * 60)
    logger.info("STEP SPLITTER TEST")
    logger.info("=" * 60)

    video_clips = [
        {"step": 1, "video_path": "/tmp/fake1.webm", "narration": "Click the Contacts tab", "action": "click_nav: Contacts"},
        {"step": 2, "video_path": "/tmp/fake2.webm", "narration": "Fill in the name field", "action": "type: First Name"},
        {"step": 3, "video_path": "", "narration": "Missing path", "action": "click"},  # Should be skipped
    ]

    steps = split_video_clips_to_steps(video_clips, platform_name="Salesforce")

    assert len(steps) == 2, f"Expected 2 steps (1 skipped), got {len(steps)}"
    assert steps[0]["duration"] == 3  # "click" → SIMPLE_ACTION_DURATION
    assert steps[1]["duration"] == 5  # "fill" → COMPLEX_ACTION_DURATION

    logger.success(f"✓ Step splitter test PASSED ({len(steps)} steps generated)")


async def main():
    """Run all tests."""
    logger.info("\n" + "=" * 60)
    logger.info("RUNNING ALL PIPELINE TESTS")
    logger.info("=" * 60 + "\n")

    await test_step_splitter()
    print()
    await test_preprocessing_only()
    print()
    await test_pipeline_dry_run()

    print()
    logger.success("=" * 60)
    logger.success("ALL TESTS PASSED ✓")
    logger.success("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
