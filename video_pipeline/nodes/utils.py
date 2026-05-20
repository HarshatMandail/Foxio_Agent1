"""
Utility functions for video concatenation (FFmpeg) and file management.
"""

import shutil
import subprocess
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


def concatenate_clips(clip_paths: list[str], job_id: str) -> Path:
    """
    Concatenate multiple video clips into a single final video using FFmpeg.
    Uses the concat demuxer with re-encoding for format consistency.
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

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list_path),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
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
