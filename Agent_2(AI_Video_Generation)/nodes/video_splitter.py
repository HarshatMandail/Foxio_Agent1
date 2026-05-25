"""
Video Splitter — Splits a single raw recording into ≤8.0s clips for Grok API.

Grok Imagine Video has a hard ~8.7s limit per API call. We split at exactly
8.0s boundaries to stay safely under the limit with no overlap.
"""

import json
import subprocess
from pathlib import Path

from loguru import logger

from config.settings import settings

MAX_CLIP_SECONDS = 8.0


def split_video_into_clips(
    raw_video_path: str,
    output_dir: Path | None = None,
    max_seconds: float = MAX_CLIP_SECONDS,
) -> list[dict]:
    """
    Split a raw .mp4 video into sequential clips of max_seconds each.

    Uses FFmpeg segment muxer for exact timing with no overlap or gap.

    Args:
        raw_video_path: Path to the merged raw .mp4 from Agent 1.
        output_dir: Directory to write clip files. Defaults to settings.clip_output_dir.
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

    # Probe total duration
    total_duration = _probe_duration(input_path)
    if not total_duration or total_duration <= 0:
        raise RuntimeError(f"[Splitter] Cannot determine video duration: {raw_video_path}")

    num_clips = int(total_duration // max_seconds) + (1 if total_duration % max_seconds > 0.1 else 0)

    logger.info(
        f"[Splitter] Splitting {input_path.name} ({total_duration:.1f}s) "
        f"into {num_clips} clips of ≤{max_seconds}s each"
    )

    # Use FFmpeg segment to split at exact boundaries
    output_pattern = str(out_dir / "split_%03d.mp4")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-c", "copy",
        "-f", "segment",
        "-segment_time", str(max_seconds),
        "-reset_timestamps", "1",
        output_pattern,
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"[Splitter] FFmpeg segment failed: {e.stderr[:300]}")
        raise RuntimeError(f"Video splitting failed: {e.stderr[:200]}") from e
    except FileNotFoundError:
        raise RuntimeError("[Splitter] FFmpeg not found. Install FFmpeg.")

    # Collect generated clips and probe their durations
    clips = []
    for clip_file in sorted(out_dir.glob("split_*.mp4")):
        clip_duration = _probe_duration(clip_file) or max_seconds
        clip_index = len(clips)

        clips.append({
            "index": clip_index,
            "path": str(clip_file),
            "start_time": clip_index * max_seconds,
            "duration": min(clip_duration, max_seconds),
        })

    logger.info(f"[Splitter] Created {len(clips)} clips from {total_duration:.1f}s source")

    for clip in clips:
        logger.info(
            f"  Clip {clip['index']:02d}: {Path(clip['path']).name} "
            f"({clip['duration']:.1f}s, starts at {clip['start_time']:.1f}s)"
        )

    return clips


def _probe_duration(video_path: Path) -> float | None:
    """Probe video duration using FFprobe."""
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(video_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=True)
        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
        return duration if duration > 0 else None
    except Exception as e:
        logger.warning(f"[Splitter] FFprobe failed for {video_path.name}: {e}")
        return None
