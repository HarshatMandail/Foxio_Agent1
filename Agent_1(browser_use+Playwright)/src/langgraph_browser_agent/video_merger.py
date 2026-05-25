"""
Video Merger — Merges all Playwright-recorded videos into a single raw .mp4.

After the browser task finishes, Playwright may have created multiple .webm files
(one per page/tab opened). This module collects them all and produces ONE
continuous raw recording using FFmpeg concat + transcode to .mp4.
"""

import logging
import subprocess
from pathlib import Path

from .config import VIDEO_CLIPS_DIR

logger = logging.getLogger(__name__)


def merge_all_recordings(output_filename: str = "raw_recording.mp4") -> str | None:
    """
    Merge all .webm recordings in VIDEO_CLIPS_DIR into a single .mp4 file.

    Uses FFmpeg concat demuxer with re-encoding to ensure all clips
    (potentially different codecs/resolutions from different tabs) merge cleanly.

    Args:
        output_filename: Name for the merged output file.

    Returns:
        Path to the merged .mp4 file, or None if no recordings found.
    """
    video_dir = Path(VIDEO_CLIPS_DIR)
    if not video_dir.exists():
        logger.warning("[VideoMerger] Video clips directory does not exist.")
        return None

    # Collect all .webm files sorted by modification time (chronological order)
    recordings = sorted(
        video_dir.glob("*.webm"),
        key=lambda f: f.stat().st_mtime,
    )

    if not recordings:
        logger.warning("[VideoMerger] No .webm recordings found to merge.")
        return None

    output_path = video_dir / output_filename

    if len(recordings) == 1:
        # Single recording — just transcode to .mp4
        logger.info(f"[VideoMerger] Single recording found, converting to .mp4: {recordings[0].name}")
        _transcode_to_mp4(recordings[0], output_path)
    else:
        # Multiple recordings — concat then transcode
        logger.info(f"[VideoMerger] Merging {len(recordings)} recordings into one .mp4...")
        for r in recordings:
            logger.info(f"  - {r.name} ({r.stat().st_size // 1024}KB)")
        _concat_and_transcode(recordings, output_path)

    if output_path.exists() and output_path.stat().st_size > 0:
        logger.info(
            f"[VideoMerger] Merged video ready: {output_path} "
            f"({output_path.stat().st_size // 1024}KB)"
        )
        return str(output_path)

    logger.error("[VideoMerger] Merge failed — output file is empty or missing.")
    return None


def _transcode_to_mp4(input_path: Path, output_path: Path) -> None:
    """Transcode a single .webm to .mp4 with H.264 + AAC."""
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
        "-c:a", "aac", "-b:a", "128k", "-ac", "2",
        "-movflags", "+faststart",
        str(output_path),
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"[VideoMerger] Transcode failed: {e.stderr[:300]}")
        raise RuntimeError(f"Video transcode failed: {e.stderr[:200]}") from e
    except FileNotFoundError:
        raise RuntimeError("[VideoMerger] FFmpeg not found. Install FFmpeg.")


def _concat_and_transcode(recordings: list[Path], output_path: Path) -> None:
    """Concat multiple .webm files into one .mp4 using FFmpeg concat demuxer."""
    concat_list = output_path.parent / "merge_list.txt"

    with open(concat_list, "w") as f:
        for rec in recordings:
            f.write(f"file '{rec.resolve()}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-r", "30",
        "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,"
               "pad=1280:720:(ow-iw)/2:(oh-ih)/2:black",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2",
        "-movflags", "+faststart",
        str(output_path),
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"[VideoMerger] Concat failed: {e.stderr[:300]}")
        raise RuntimeError(f"Video concat failed: {e.stderr[:200]}") from e
    except FileNotFoundError:
        raise RuntimeError("[VideoMerger] FFmpeg not found. Install FFmpeg.")
    finally:
        concat_list.unlink(missing_ok=True)
