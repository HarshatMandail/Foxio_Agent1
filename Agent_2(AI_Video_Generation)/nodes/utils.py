"""
Utility functions for video concatenation (FFmpeg), preprocessing, and file management.
"""

import json
import shutil
import subprocess
import uuid
from pathlib import Path

from loguru import logger

from config.settings import settings


def ensure_directories() -> None:
    """Create required output directories if they don't exist."""
    settings.clip_output_dir.mkdir(parents=True, exist_ok=True)
    settings.final_output_dir.mkdir(parents=True, exist_ok=True)


def cleanup_clips() -> None:
    """Remove all temporary clip files after concatenation."""
    if settings.clip_output_dir.exists():
        shutil.rmtree(settings.clip_output_dir)
        logger.info(f"Cleaned up clips directory: {settings.clip_output_dir}")


def cleanup_preprocessed() -> None:
    """Remove all temporary preprocessed .mp4 files after final video is produced."""
    if not settings.cleanup_temp_files:
        logger.info("[Cleanup] Skipping preprocessed cleanup (cleanup_temp_files=False)")
        return

    if settings.preprocess_output_dir.exists():
        file_count = len(list(settings.preprocess_output_dir.glob("*.mp4")))
        shutil.rmtree(settings.preprocess_output_dir)
        logger.info(
            f"[Cleanup] Removed {file_count} preprocessed files: "
            f"{settings.preprocess_output_dir}"
        )


def concatenate_clips(clip_paths: list[str], job_id: str) -> Path:
    """
    Concatenate multiple video clips into a single final video using FFmpeg.

    Uses concat demuxer with re-encoding for format consistency.
    Applies consistent encoding settings for a professional output:
      - H.264 with CRF 18 (high quality)
      - yuv420p for maximum compatibility
      - faststart for web streaming
    """
    if not clip_paths:
        raise ValueError("No clips to concatenate")

    settings.final_output_dir.mkdir(parents=True, exist_ok=True)
    output_path = settings.final_output_dir / f"tutorial_{job_id}.mp4"

    concat_list_path = settings.clip_output_dir / "concat_list.txt"
    with open(concat_list_path, "w") as f:
        for clip_path in sorted(clip_paths):
            absolute_path = Path(clip_path).resolve()
            f.write(f"file '{absolute_path}'\n")

    logger.info(f"Concatenating {len(clip_paths)} clips into: {output_path}")

    # High-quality encoding for professional tutorial output
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list_path),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-r", "60",              # Force 60fps output for smooth playback
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]

    try:
        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            check=True,
        )
        logger.success(f"Final video created: {output_path}")
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg failed: {e.stderr}")
        raise RuntimeError(f"FFmpeg concatenation failed: {e.stderr}") from e
    except FileNotFoundError:
        raise RuntimeError(
            "FFmpeg not found. Install FFmpeg and ensure it's in PATH."
        )

    return output_path


def preprocess_video_for_grok(video_path: str) -> str:
    """
    Preprocess a raw Playwright .webm recording for Grok Imagine Video edit-video mode.

    Steps:
      1. Convert .webm → .mp4 (H.264 video + AAC audio)
      2. Trim to max duration (keeps the last N seconds where the action happens)
      3. Normalize FPS to configured value (30 or 60)
      4. Scale to configured resolution (1280x720 or 1920x1080)

    Args:
        video_path: Path to the raw .webm (or any video) from Playwright.

    Returns:
        Path to the processed .mp4 file ready for upload to xAI.

    Raises:
        RuntimeError: If FFmpeg fails or input file doesn't exist.
    """
    input_path = Path(video_path)
    if not input_path.exists():
        raise RuntimeError(f"[Preprocess] Input video not found: {video_path}")

    settings.preprocess_output_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique output filename
    clip_id = uuid.uuid4().hex[:8]
    output_path = settings.preprocess_output_dir / f"{input_path.stem}_{clip_id}.mp4"

    max_duration = settings.preprocess_max_duration
    fps = settings.preprocess_fps
    width = settings.preprocess_width
    height = settings.preprocess_height

    # Probe input duration to decide trim strategy
    input_duration = _probe_duration(input_path)

    # Build FFmpeg command
    cmd = ["ffmpeg", "-y"]

    # If input is longer than max, seek to keep the LAST N seconds (where action occurs)
    if input_duration and input_duration > max_duration:
        seek_to = input_duration - max_duration
        cmd.extend(["-ss", f"{seek_to:.2f}"])
        logger.info(
            f"[Preprocess] Trimming: {input_duration:.1f}s → last {max_duration}s "
            f"(seeking to {seek_to:.1f}s)"
        )

    cmd.extend(["-i", str(input_path)])

    # Duration limit (hard cap)
    cmd.extend(["-t", str(max_duration)])

    # Video: H.264, target FPS, scaled resolution, pixel format for compatibility
    cmd.extend([
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        "-r", str(fps),
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
               f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
        "-pix_fmt", "yuv420p",
    ])

    # Audio: AAC (or silent if no audio stream)
    cmd.extend(["-c:a", "aac", "-b:a", "128k", "-ac", "2"])

    # Fast-start for streaming compatibility
    cmd.extend(["-movflags", "+faststart"])

    cmd.append(str(output_path))

    logger.info(
        f"[Preprocess] Converting: {input_path.name} → {output_path.name} | "
        f"fps={fps} | res={width}x{height} | max_dur={max_duration}s"
    )

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
        logger.success(f"[Preprocess] Done: {output_path} ({output_path.stat().st_size // 1024}KB)")
    except subprocess.CalledProcessError as e:
        logger.error(f"[Preprocess] FFmpeg failed: {e.stderr[:500]}")
        raise RuntimeError(f"Video preprocessing failed: {e.stderr[:200]}") from e
    except FileNotFoundError:
        raise RuntimeError(
            "[Preprocess] FFmpeg not found. Install FFmpeg and ensure it's in PATH."
        )

    return str(output_path)


def _probe_duration(video_path: Path) -> float | None:
    """
    Probe video duration using FFprobe.

    Returns duration in seconds, or None if probing fails.
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(video_path),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )

        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
        return duration if duration > 0 else None

    except Exception as e:
        logger.warning(f"[Preprocess] FFprobe failed, skipping trim optimization: {e}")
        return None
