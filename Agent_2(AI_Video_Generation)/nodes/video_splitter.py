"""
Video Splitter — Splits a raw recording into overlapping clips for Grok API.

Grok Imagine Video has a ~8.7s limit per call. We create 8s clips
with 1s overlap for smooth cross-fade transitions during concatenation.
"""

import subprocess
from pathlib import Path

from loguru import logger

from config.settings import settings
from nodes.utils import probe_duration

CLIP_DURATION = 8.0
OVERLAP_SECONDS = 1.0
STEP_SECONDS = CLIP_DURATION - OVERLAP_SECONDS


def split_video_into_clips(
    raw_video_path: str,
    output_dir: Path | None = None,
    max_seconds: float = CLIP_DURATION,
) -> list[dict]:
    """
    Split a raw .mp4 video into overlapping clips for Grok API.

    Each clip is 8s long. Consecutive clips overlap by 1s:
      clip_0: 0.0 - 8.0s
      clip_1: 7.0 - 15.0s
      clip_2: 14.0 - 22.0s

    Args:
        raw_video_path: Path to the merged raw .mp4 from Agent 1.
        output_dir: Directory to write clip files.
        max_seconds: Maximum duration per clip (default 8.0s).

    Returns:
        List of dicts with keys: index, path, start_time, duration.

    Raises:
        RuntimeError: If FFmpeg fails or input doesn't exist.
    """
    input_path = Path(raw_video_path)
    if not input_path.exists():
        raise RuntimeError(f"[Splitter] Input video not found: {raw_video_path}")

    out_dir = output_dir or settings.clip_output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    total_duration = probe_duration(input_path)
    if not total_duration or total_duration <= 0:
        raise RuntimeError(f"[Splitter] Cannot determine video duration: {raw_video_path}")

    clip_starts = _calculate_clip_starts(total_duration)

    logger.info(
        f"[Splitter] Splitting {input_path.name} ({total_duration:.1f}s) "
        f"into {len(clip_starts)} clips of ≤{max_seconds}s with {OVERLAP_SECONDS}s overlap"
    )

    clips = []
    for i, start in enumerate(clip_starts):
        remaining = total_duration - start
        duration = min(max_seconds, remaining)

        if duration < 1.0:
            break

        output_file = out_dir / f"split_{i:03d}.mp4"
        _extract_clip(input_path, output_file, start, duration, i)

        actual_duration = probe_duration(output_file) or duration

        clips.append({
            "index": i,
            "path": str(output_file),
            "start_time": start,
            "duration": actual_duration,
        })

    logger.info(f"[Splitter] Created {len(clips)} clips from {total_duration:.1f}s source")
    return clips


def _calculate_clip_starts(total_duration: float) -> list[float]:
    """Calculate clip start times with overlap."""
    starts = []
    t = 0.0
    while t < total_duration:
        starts.append(t)
        t += STEP_SECONDS
        if t >= total_duration and (total_duration - starts[-1]) < 1.0:
            break
    return starts


def _extract_clip(input_path: Path, output_file: Path, start: float, duration: float, index: int) -> None:
    """Extract a single clip using FFmpeg."""
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}",
        "-i", str(input_path),
        "-t", f"{duration:.3f}",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-r", "30",
        "-pix_fmt", "yuv420p",
        "-an",
        "-movflags", "+faststart",
        str(output_file),
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Splitting failed at clip {index}: {e.stderr[:200]}") from e
    except FileNotFoundError:
        raise RuntimeError("[Splitter] FFmpeg not found. Install FFmpeg.")
