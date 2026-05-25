# video_converter.py — Convert Playwright .webm recordings to Grok-compatible .mp4
import json
import logging
import subprocess
from pathlib import Path

from .config import VIDEO_CLIPS_DIR

logger = logging.getLogger(__name__)

# Grok Imagine Video compatible encoding settings
FFMPEG_SETTINGS = {
    "codec": "libx264",
    "preset": "medium",
    "crf": "18",
    "fps": "30",
    "pix_fmt": "yuv420p",
    "audio_codec": "aac",
    "audio_bitrate": "128k",
}


def convert_webm_to_mp4(webm_path: str) -> str:
    """
    Convert a single .webm file to .mp4 with Grok-compatible settings.

    Args:
        webm_path: Path to the .webm file.

    Returns:
        Path to the converted .mp4 file.

    Raises:
        RuntimeError: If ffmpeg fails or input doesn't exist.
    """
    input_path = Path(webm_path)
    if not input_path.exists():
        raise RuntimeError(f"Input video not found: {webm_path}")

    output_path = input_path.with_suffix(".mp4")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-c:v", FFMPEG_SETTINGS["codec"],
        "-preset", FFMPEG_SETTINGS["preset"],
        "-crf", FFMPEG_SETTINGS["crf"],
        "-r", FFMPEG_SETTINGS["fps"],
        "-pix_fmt", FFMPEG_SETTINGS["pix_fmt"],
        "-c:a", FFMPEG_SETTINGS["audio_codec"],
        "-b:a", FFMPEG_SETTINGS["audio_bitrate"],
        "-ac", "2",
        "-movflags", "+faststart",
        str(output_path),
    ]

    logger.info(f"[Converter] {input_path.name} → {output_path.name}")

    try:
        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"[Converter] FFmpeg failed: {e.stderr[:300]}")
        raise RuntimeError(f"FFmpeg conversion failed: {e.stderr[:200]}") from e
    except FileNotFoundError:
        raise RuntimeError(
            "[Converter] FFmpeg not found. Install FFmpeg and add it to PATH."
        )

    size_kb = output_path.stat().st_size // 1024
    logger.info(f"[Converter] Done: {output_path.name} ({size_kb}KB)")

    return str(output_path)


def convert_all_clips(video_clips: list[dict]) -> list[dict]:
    """
    Convert all .webm video clips to .mp4 in-place.

    Updates each clip's video_path to point to the new .mp4 file.
    Skips clips that are already .mp4 or have missing files.

    Args:
        video_clips: List of clip dicts with 'video_path' key.

    Returns:
        Updated list with video_path pointing to .mp4 files.
    """
    if not video_clips:
        return video_clips

    logger.info(f"[Converter] Converting {len(video_clips)} clips: .webm → .mp4")

    converted = []
    for clip in video_clips:
        video_path = clip.get("video_path", "")
        if not video_path:
            converted.append(clip)
            continue

        path = Path(video_path)

        # Already .mp4 — skip
        if path.suffix.lower() == ".mp4":
            converted.append(clip)
            continue

        # File doesn't exist — skip with warning
        if not path.exists():
            logger.warning(f"[Converter] Skipping missing file: {video_path}")
            converted.append(clip)
            continue

        try:
            mp4_path = convert_webm_to_mp4(video_path)
            updated_clip = {**clip, "video_path": mp4_path}
            converted.append(updated_clip)
        except RuntimeError as e:
            logger.error(f"[Converter] Failed to convert {path.name}: {e}")
            converted.append(clip)

    successful = sum(
        1 for c in converted
        if Path(c.get("video_path", "")).suffix.lower() == ".mp4"
    )
    logger.info(f"[Converter] Complete: {successful}/{len(converted)} clips as .mp4")

    return converted
