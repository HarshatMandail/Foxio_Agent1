"""
Video Merger — Collects, filters, sorts, and merges Playwright video recordings.

After the browser task finishes, Playwright creates multiple .webm files (one per
page/tab). This module:
  1. Collects all .webm files from the recording directory.
  2. Sorts by file creation time (os.path.getctime) for real chronological order.
  3. Filters out useless clips (< 2s duration, mostly blank/white frames).
  4. Merges valid clips into ONE raw video using ffmpeg concat.
  5. Saves metadata JSON with clip list, order, durations, and discard reasons.
"""

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

from .config import VIDEO_CLIPS_DIR, OUTPUT_DIR

logger = logging.getLogger(__name__)

MIN_CLIP_DURATION_SEC = 2.0
BLANK_FRAME_THRESHOLD = 250  # Mean pixel value above this = "white/blank"
BLANK_FRAME_RATIO = 0.85  # If >85% of sampled frames are blank, skip clip


def clean_old_clips() -> None:
    """Remove all .webm and .mp4 files from VIDEO_CLIPS_DIR before a new session."""
    video_dir = Path(VIDEO_CLIPS_DIR)
    if not video_dir.exists():
        return

    removed = 0
    for ext in ("*.webm", "*.mp4"):
        for f in video_dir.glob(ext):
            f.unlink()
            removed += 1

    if removed:
        logger.info(f"[VideoMerger] Cleaned {removed} old clips from {video_dir}")


def convert_clips_to_mp4() -> list[Path]:
    """
    Convert all .webm clips in VIDEO_CLIPS_DIR to .mp4 in-place.
    Deletes the original .webm after successful conversion.

    Returns:
        List of converted .mp4 file paths.
    """
    video_dir = Path(VIDEO_CLIPS_DIR)
    if not video_dir.exists():
        return []

    webm_files = list(video_dir.glob("*.webm"))
    if not webm_files:
        logger.info("[VideoMerger] No .webm files to convert.")
        return []

    logger.info(f"[VideoMerger] Converting {len(webm_files)} .webm clips to .mp4...")
    converted = []

    for webm_path in webm_files:
        mp4_path = webm_path.with_suffix(".mp4")
        try:
            _transcode_to_mp4(webm_path, mp4_path)
            # Delete original .webm after successful conversion
            webm_path.unlink()
            converted.append(mp4_path)
            logger.info(f"  [OK] {webm_path.name} → {mp4_path.name}")
        except Exception as e:
            logger.warning(f"  [FAIL] {webm_path.name}: {e}")

    logger.info(f"[VideoMerger] Converted {len(converted)}/{len(webm_files)} clips to .mp4")
    return converted


def merge_all_recordings(
    output_filename: str = "raw_long_video.mp4",
    output_dir: Optional[Path] = None,
    trim_start: float = 0,
) -> Optional[str]:
    """
    Convert .webm -> .mp4, filter junk, and merge into one output file.

    Args:
        output_filename: Name for the merged output file.
        output_dir: Directory for the output.
        trim_start: Deprecated, kept for API compatibility.

    Returns:
        Path to the final .mp4 file, or None if no valid recordings found.
    """
    video_dir = Path(VIDEO_CLIPS_DIR)
    dest_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    if not video_dir.exists():
        logger.warning("[VideoMerger] Video clips directory does not exist.")
        return None

    convert_clips_to_mp4()

    all_recordings = sorted(
        video_dir.glob("*.mp4"),
        key=lambda f: os.path.getctime(f),
    )

    if not all_recordings:
        logger.warning("[VideoMerger] No .mp4 recordings found after conversion.")
        return None

    logger.info(f"[VideoMerger] Found {len(all_recordings)} .mp4 clips. Filtering...")

    valid_clips = []
    discarded_clips = []

    for clip_path in all_recordings:
        duration = _get_clip_duration(clip_path)
        discard_reason = None

        if duration is None or duration < MIN_CLIP_DURATION_SEC:
            discard_reason = f"too_short ({duration:.1f}s)" if duration else "unreadable"
        elif _is_mostly_blank(clip_path):
            discard_reason = "mostly_blank"

        if discard_reason:
            discarded_clips.append({"file": clip_path.name, "duration": duration, "reason": discard_reason})
            logger.info(f"  [SKIP] {clip_path.name} — {discard_reason}")
        else:
            valid_clips.append({"file": clip_path.name, "path": str(clip_path), "duration": duration, "ctime": os.path.getctime(clip_path)})
            logger.info(f"  [KEEP] {clip_path.name} — {duration:.1f}s")

    if not valid_clips:
        logger.warning("[VideoMerger] All clips were filtered out. No valid recordings.")
        _save_metadata(dest_dir, [], discarded_clips, None)
        return None

    output_path = dest_dir / output_filename

    if len(valid_clips) == 1:
        _remux_mp4(Path(valid_clips[0]["path"]), output_path)
    else:
        logger.info(f"[VideoMerger] Merging {len(valid_clips)} valid .mp4 clips...")
        _concat_mp4_clips([Path(c["path"]) for c in valid_clips], output_path)

    if output_path.exists() and output_path.stat().st_size > 0:
        total_duration = _get_clip_duration(output_path) or 0
        logger.info(f"[VideoMerger] Done: {output_path} ({output_path.stat().st_size // 1024}KB, ~{total_duration:.1f}s)")
        _save_metadata(dest_dir, valid_clips, discarded_clips, str(output_path))
        # Clean up intermediate clips from video_clips dir
        _cleanup_intermediate_clips(video_dir)
        return str(output_path)

    logger.error("[VideoMerger] Merge failed — output file missing or empty.")
    _save_metadata(dest_dir, valid_clips, discarded_clips, None)
    return None


# ─── Filtering Helpers ────────────────────────────────────────────────────────


def _get_clip_duration(clip_path: Path) -> Optional[float]:
    """Get clip duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(clip_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        return float(data.get("format", {}).get("duration", 0))
    except Exception:
        return None


def _is_mostly_blank(clip_path: Path) -> bool:
    """Check if a clip is mostly white/blank by sampling frames with ffmpeg."""
    # Extract 5 evenly-spaced frames and check average brightness
    cmd = [
        "ffprobe", "-v", "quiet",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-print_format", "json",
        str(clip_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return False

        # Use signalstats filter to get average brightness of sampled frames
        cmd_stats = [
            "ffmpeg", "-v", "quiet",
            "-i", str(clip_path),
            "-vf", "fps=1,signalstats",
            "-f", "null", "-",
        ]
        stats_result = subprocess.run(
            cmd_stats, capture_output=True, text=True, timeout=30,
        )

        # Parse lavfi output for YAVG (luma average)
        stderr = stats_result.stderr
        if not stderr:
            return False

        yavg_values = []
        for line in stderr.split("\n"):
            if "YAVG" in line:
                try:
                    idx = line.index("YAVG:") + 5
                    val = float(line[idx:].split()[0])
                    yavg_values.append(val)
                except (ValueError, IndexError):
                    continue

        if not yavg_values:
            return False

        blank_frames = sum(1 for v in yavg_values if v > BLANK_FRAME_THRESHOLD)
        ratio = blank_frames / len(yavg_values)
        return ratio >= BLANK_FRAME_RATIO

    except Exception:
        return False


# ─── FFmpeg Operations ────────────────────────────────────────────────────────


def _transcode_to_mp4(input_path: Path, output_path: Path) -> None:
    """Transcode a single .webm to .mp4 with H.264 (Grok Imagine compatible)."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-r", "30",
        "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,"
               "pad=1280:720:(ow-iw)/2:(oh-ih)/2:black",
        "-pix_fmt", "yuv420p",
        "-an",
        "-movflags", "+faststart",
        str(output_path),
    ]
    _run_ffmpeg(cmd, "transcode")


def _remux_mp4(input_path: Path, output_path: Path) -> None:
    """Re-mux an existing .mp4 to ensure consistent format (no re-encoding)."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-c", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]
    _run_ffmpeg(cmd, "remux")


def _concat_mp4_clips(recordings: list[Path], output_path: Path) -> None:
    """Concat multiple .mp4 files into one using ffmpeg concat demuxer (no re-encoding)."""
    concat_list = output_path.parent / "_merge_list.txt"

    with open(concat_list, "w", encoding="utf-8") as f:
        for rec in recordings:
            f.write(f"file '{rec.resolve()}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]

    try:
        _run_ffmpeg(cmd, "concat")
    finally:
        concat_list.unlink(missing_ok=True)


def _run_ffmpeg(cmd: list[str], operation: str) -> None:
    """Execute an ffmpeg command with error handling."""
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"[VideoMerger] {operation} failed: {e.stderr[:300]}")
        raise RuntimeError(f"FFmpeg {operation} failed: {e.stderr[:200]}") from e
    except FileNotFoundError:
        raise RuntimeError("[VideoMerger] FFmpeg not found. Install FFmpeg.")


# ─── Metadata ─────────────────────────────────────────────────────────────────


def _cleanup_intermediate_clips(video_dir: Path) -> None:
    """Remove all .mp4/.webm files from the video_clips dir after merge."""
    for ext in ("*.mp4", "*.webm"):
        for f in video_dir.glob(ext):
            f.unlink()
    logger.info(f"[VideoMerger] Cleaned intermediate clips from {video_dir}")


def _save_metadata(
    dest_dir: Path,
    valid_clips: list[dict],
    discarded_clips: list[dict],
    output_path: Optional[str],
) -> None:
    """Save merge metadata JSON alongside the output video."""
    metadata = {
        "output_video": output_path,
        "total_valid_clips": len(valid_clips),
        "total_discarded_clips": len(discarded_clips),
        "total_duration_sec": sum(c.get("duration", 0) for c in valid_clips),
        "clips_in_order": [
            {"file": c["file"], "duration_sec": c["duration"]}
            for c in valid_clips
        ],
        "discarded": discarded_clips,
    }

    metadata_path = dest_dir / "merge_metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, default=str),
        encoding="utf-8",
    )
    logger.info(f"[VideoMerger] Metadata saved: {metadata_path}")
