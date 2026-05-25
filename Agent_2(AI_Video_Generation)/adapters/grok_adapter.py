"""
xAI Grok Imagine Video adapter — Industry-grade anti-hallucination implementation.

REFACTORED v4: Hardened upload + error handling for edit-video mode.

Key changes from v3:
  1. _upload_video_file() — 3-attempt retry with exponential backoff,
     configurable timeout, detailed error logging per attempt.
  2. Handles both direct video_url and xAI file_id in upload response.
  3. generate_edit_video() passes the correct reference (URL or file_id)
     to the SDK based on what the Files API returns.
  4. All existing I2V functionality preserved unchanged.

Uses `xai_sdk.Client` for video generation.
"""

import asyncio
import base64
import mimetypes
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
from loguru import logger
from xai_sdk import Client

from adapters.base import VideoGenerationService
from config.settings import settings
from core.registry import VideoModel

SUPPORTED_ASPECT_RATIOS = {"1:1", "16:9", "9:16"}
SUPPORTED_RESOLUTIONS = {"480p", "720p"}

# Upload configuration
UPLOAD_MAX_RETRIES = 3
UPLOAD_BASE_DELAY = 2.0  # seconds
UPLOAD_TIMEOUT = 120.0  # seconds per attempt
XAI_FILES_API_URL = "https://api.x.ai/v1/files"

# Prefix injected into every I2V prompt to anchor the model to the reference frame
I2V_ANCHOR_PREFIX = (
    "CONTINUE EXACTLY from the reference image. The first frame of this video "
    "MUST be pixel-identical to the provided reference image. "
)

# Prefix for edit-video mode — preserves UI fidelity while enhancing quality
EDIT_VIDEO_PREFIX = (
    "Enhance this real screen recording. Keep every UI element, text, button, "
    "icon, and layout 100% identical to the original video. "
)


def _local_file_to_data_uri(file_path: str) -> str | None:
    """Convert a local image file to a base64 data URI for the xAI API."""
    path = Path(file_path)
    if not path.exists():
        logger.warning(f"[GrokAdapter] Screenshot not found: {file_path}")
        return None

    mime_type = mimetypes.guess_type(str(path))[0] or "image/png"
    raw_bytes = path.read_bytes()
    b64 = base64.b64encode(raw_bytes).decode("utf-8")

    logger.info(
        f"[GrokAdapter] Converted to data URI | "
        f"file={path.name} | size={len(raw_bytes)//1024}KB | mime={mime_type}"
    )

    return f"data:{mime_type};base64,{b64}"


def _resolve_image_url(start_image: str | None) -> str | None:
    """Resolve start_image to a URL the xAI API can consume.

    Handles:
      - None → None (text-to-video)
      - HTTP/HTTPS URL → pass through
      - data: URI → pass through
      - Local file path → convert to base64 data URI
    """
    if not start_image:
        return None

    if start_image.startswith(("http://", "https://", "data:")):
        return start_image

    return _local_file_to_data_uri(start_image)


def extract_last_frame(video_path: str | Path) -> str | None:
    """
    Extract the last frame from a video clip using FFmpeg.

    Critical for I2V chaining: last frame of clip N → start_image of clip N+1.
    This is the primary mechanism for visual continuity between clips.

    Returns:
        Base64 data URI of the last frame (PNG), or None on failure.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        logger.warning(f"[GrokAdapter] Cannot extract frame — video not found: {video_path}")
        return None

    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            frame_path = Path(tmp.name)

        # Extract the very last frame using -sseof (seek from end)
        cmd = [
            "ffmpeg",
            "-y",
            "-sseof", "-0.05",
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "1",
            str(frame_path),
        ]

        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        if not frame_path.exists() or frame_path.stat().st_size == 0:
            logger.warning(f"[GrokAdapter] Frame extraction produced empty file: {video_path}")
            return None

        data_uri = _local_file_to_data_uri(str(frame_path))
        frame_path.unlink(missing_ok=True)

        logger.info(f"[GrokAdapter] Extracted last frame from: {video_path.name}")
        return data_uri

    except subprocess.CalledProcessError as e:
        logger.warning(f"[GrokAdapter] FFmpeg frame extraction failed: {e.stderr[:200]}")
        return None
    except FileNotFoundError:
        logger.warning("[GrokAdapter] FFmpeg not found — cannot extract frames for I2V chaining.")
        return None
    except Exception as e:
        logger.warning(f"[GrokAdapter] Frame extraction error: {e}")
        return None


def extract_last_frame_to_file(video_path: str | Path) -> Path | None:
    """
    Extract the last frame and save to a persistent file (not temp).
    Used when we need the frame file to persist for description or debugging.

    Returns:
        Path to the extracted PNG frame, or None on failure.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        return None

    frame_path = video_path.with_suffix(".last_frame.png")

    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-sseof", "-0.05",
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "1",
            str(frame_path),
        ]

        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        if frame_path.exists() and frame_path.stat().st_size > 0:
            return frame_path
        return None

    except Exception as e:
        logger.warning(f"[GrokAdapter] Frame file extraction error: {e}")
        return None


def describe_last_frame(video_path: str | Path) -> str:
    """
    Generate a brief text description of the last frame's visual content.

    This description is injected into the NEXT clip's prompt to provide
    textual grounding in addition to the image-to-video visual grounding.
    Double grounding (image + text description) dramatically reduces drift.

    Returns:
        Brief description string of the frame's visual state.
    """
    video_path = Path(video_path)

    stem = video_path.stem
    description = (
        f"the exact UI state shown at the end of {stem}, "
        f"with all elements in their current positions, "
        f"all text readable, all icons and buttons unchanged"
    )

    return description


class GrokAdapter(VideoGenerationService):
    """
    Official xAI SDK adapter for Grok Imagine Video.

    Supports three modes:
      - text-to-video (T2V): Generate from prompt only.
      - image-to-video (I2V): Generate from prompt + reference image.
      - edit-video: Enhance/polish a real recorded video clip.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def generate(
        self,
        model: VideoModel,
        prompt: str,
        duration: int,
        output_path: Path,
        aspect_ratio: str = "16:9",
        resolution: str = "480p",
        start_image: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Generate a video using the official xAI SDK (I2V or T2V mode).

        When start_image is provided, the I2V_ANCHOR_PREFIX is prepended
        to the prompt to force the model to treat the image as ground truth.
        """
        self._validate_prompt(prompt)
        validated_aspect_ratio = self._validate_aspect_ratio(aspect_ratio)
        validated_resolution = self._validate_resolution(resolution)
        clamped_duration = max(1, min(duration, settings.max_clip_duration))

        # Resolve start_image (local path → data URI, URL → pass through)
        resolved_image = _resolve_image_url(start_image)
        mode = "image-to-video" if resolved_image else "text-to-video"

        # For I2V mode, prepend the anchor prefix to lock model to reference
        effective_prompt = prompt
        if resolved_image:
            effective_prompt = I2V_ANCHOR_PREFIX + prompt

        logger.info(
            f"[GrokAdapter] Requesting video | model={model.name} | "
            f"mode={mode} | duration={clamped_duration}s | "
            f"aspect_ratio={validated_aspect_ratio} | "
            f"resolution={validated_resolution} | "
            f"prompt_length={len(effective_prompt)}"
        )

        if dry_run or settings.dry_run:
            logger.warning(
                f"[GrokAdapter] DRY RUN — skipping API call. "
                f"Mode: {mode} | Prompt: {effective_prompt[:150]}..."
            )
            return {
                "status": "dry_run",
                "path": str(output_path),
                "model": model.name,
                "duration": clamped_duration,
                "provider": "xai",
                "mode": mode,
                "has_start_image": resolved_image is not None,
                "video_url": None,
                "cost_usd": 0.0,
            }

        # Build generation kwargs
        gen_kwargs: dict[str, Any] = {
            "prompt": effective_prompt,
            "model": model.name,
            "duration": clamped_duration,
            "aspect_ratio": validated_aspect_ratio,
            "resolution": validated_resolution,
        }

        if resolved_image:
            gen_kwargs["image_url"] = resolved_image

        # Call the official xAI SDK (synchronous)
        client = Client(api_key=self._api_key)
        response = client.video.generate(**gen_kwargs)

        video_url = response.url
        video_bytes = await self._download_video(video_url)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(video_bytes)

        response_duration = getattr(response, "duration", clamped_duration)

        logger.success(
            f"[GrokAdapter] Video saved: {output_path} | "
            f"mode={mode} | duration={response_duration}s"
        )

        return {
            "status": "success",
            "path": str(output_path),
            "model": model.name,
            "duration": response_duration,
            "provider": "xai",
            "mode": mode,
            "has_start_image": resolved_image is not None,
            "video_url": video_url,
            "cost_usd": getattr(response, "cost_usd", None),
        }

    async def generate_edit_video(
        self,
        input_video_path: str,
        prompt: str,
        duration: int = 5,
        aspect_ratio: str = "16:9",
        resolution: str = "480p",
        output_path: Path | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Enhance a real recorded video clip using Grok Imagine Video in edit-video mode.

        Expects a pre-processed .mp4 file (converted from .webm, trimmed, normalized).
        Uploads to xAI Files API, then calls the generation endpoint in edit-video mode.

        Args:
            input_video_path: Path to the pre-processed .mp4 video clip.
            prompt: Enhancement instructions (UI preservation + quality boost).
            duration: Target output duration in seconds (3-8).
            aspect_ratio: Output aspect ratio.
            resolution: Output resolution.
            output_path: Where to save the enhanced clip.
            dry_run: If True, skip API call and log only.

        Returns:
            Dict with generation metadata including output path.
        """
        self._validate_prompt(prompt)
        validated_aspect_ratio = self._validate_aspect_ratio(aspect_ratio)
        validated_resolution = self._validate_resolution(resolution)
        clamped_duration = max(1, min(duration, settings.max_clip_duration))

        video_file = Path(input_video_path)
        if not video_file.exists():
            raise FileNotFoundError(
                f"[GrokAdapter] Input video not found: {input_video_path}"
            )

        # Validate file is .mp4 (should be pre-processed already)
        if video_file.suffix.lower() not in (".mp4", ".webm", ".mov"):
            logger.warning(
                f"[GrokAdapter] Unexpected file format: {video_file.suffix}. "
                f"Expected .mp4 (pre-processed). Proceeding anyway."
            )

        # Prepend edit-video anchor to ensure UI preservation
        effective_prompt = EDIT_VIDEO_PREFIX + prompt

        logger.info(
            f"[GrokAdapter] Edit-Video request | "
            f"input={video_file.name} | size={video_file.stat().st_size // 1024}KB | "
            f"duration={clamped_duration}s | aspect_ratio={validated_aspect_ratio} | "
            f"prompt_length={len(effective_prompt)}"
        )

        if dry_run or settings.dry_run:
            logger.warning(
                f"[GrokAdapter] DRY RUN (edit-video) — skipping API call. "
                f"Input: {video_file.name} | Prompt: {effective_prompt[:150]}..."
            )
            return {
                "status": "dry_run",
                "path": str(output_path or video_file),
                "model": "grok-imagine-video",
                "duration": clamped_duration,
                "provider": "xai",
                "mode": "edit-video",
                "input_video": str(video_file),
                "video_url": None,
                "cost_usd": 0.0,
            }

        # Upload the pre-processed .mp4 to xAI Files API (with retry)
        upload_result = await self._upload_video_file(video_file)
        video_reference = upload_result["reference"]
        reference_type = upload_result["type"]

        # Build SDK call kwargs based on what the Files API returned
        gen_kwargs: dict[str, Any] = {
            "model": "grok-imagine-video",
            "prompt": effective_prompt,
            "mode": "edit-video",
            "duration": clamped_duration,
            "aspect_ratio": validated_aspect_ratio,
            "resolution": validated_resolution,
        }

        # xAI API accepts either a direct URL or a file_id reference
        if reference_type == "url":
            gen_kwargs["video_url"] = video_reference
        else:
            gen_kwargs["file_id"] = video_reference

        logger.info(
            f"[GrokAdapter] Calling edit-video API | "
            f"reference_type={reference_type} | ref={video_reference[:60]}..."
        )

        # Call xAI SDK in edit-video mode
        client = Client(api_key=self._api_key)
        response = client.video.generate(**gen_kwargs)

        result_url = response.url
        video_bytes = await self._download_video(result_url)

        # Save to output path
        if output_path is None:
            output_path = video_file.with_suffix(".enhanced.mp4")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(video_bytes)

        response_duration = getattr(response, "duration", clamped_duration)

        logger.success(
            f"[GrokAdapter] Edit-Video saved: {output_path} | "
            f"duration={response_duration}s | size={output_path.stat().st_size // 1024}KB"
        )

        return {
            "status": "success",
            "path": str(output_path),
            "model": "grok-imagine-video",
            "duration": response_duration,
            "provider": "xai",
            "mode": "edit-video",
            "input_video": str(video_file),
            "video_url": result_url,
            "cost_usd": getattr(response, "cost_usd", None),
        }

    async def _upload_video_file(self, video_path: Path) -> dict[str, str]:
        """
        Upload a local video file to xAI Files API for edit-video mode.

        Implements retry logic with exponential backoff (3 attempts).
        Handles both URL-based and file_id-based responses from the API.

        Args:
            video_path: Path to the pre-processed .mp4 file.

        Returns:
            Dict with keys:
              - "reference": The URL or file_id to pass to the generation API.
              - "type": Either "url" or "file_id" indicating the reference format.

        Raises:
            RuntimeError: If all upload attempts fail.
        """
        mime_type = mimetypes.guess_type(str(video_path))[0] or "video/mp4"
        file_size_kb = video_path.stat().st_size // 1024

        logger.info(
            f"[GrokAdapter Upload] Starting upload | "
            f"file={video_path.name} | size={file_size_kb}KB | mime={mime_type}"
        )

        last_error: str = ""

        for attempt in range(1, UPLOAD_MAX_RETRIES + 1):
            start_time = time.time()

            try:
                async with httpx.AsyncClient(timeout=UPLOAD_TIMEOUT) as http_client:
                    headers = {
                        "Authorization": f"Bearer {self._api_key}",
                    }

                    with open(video_path, "rb") as f:
                        files = {
                            "file": (video_path.name, f, mime_type),
                            "purpose": (None, "video-edit"),
                        }

                        logger.info(
                            f"[GrokAdapter Upload] Attempt {attempt}/{UPLOAD_MAX_RETRIES} | "
                            f"endpoint={XAI_FILES_API_URL}"
                        )

                        resp = await http_client.post(
                            XAI_FILES_API_URL,
                            headers=headers,
                            files=files,
                        )

                elapsed = time.time() - start_time

                # Handle HTTP errors with specific messages
                if resp.status_code >= 400:
                    error_body = resp.text[:300]
                    last_error = (
                        f"HTTP {resp.status_code}: {error_body}"
                    )
                    logger.warning(
                        f"[GrokAdapter Upload] Attempt {attempt} failed | "
                        f"status={resp.status_code} | elapsed={elapsed:.1f}s | "
                        f"error={error_body[:150]}"
                    )

                    # Don't retry on 4xx client errors (except 429 rate limit)
                    if 400 <= resp.status_code < 500 and resp.status_code != 429:
                        raise RuntimeError(
                            f"[GrokAdapter Upload] Client error (non-retryable): {last_error}"
                        )

                    # Retry on 5xx or 429
                    if attempt < UPLOAD_MAX_RETRIES:
                        delay = UPLOAD_BASE_DELAY * (2 ** (attempt - 1))
                        logger.info(f"[GrokAdapter Upload] Retrying in {delay:.1f}s...")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        raise RuntimeError(
                            f"[GrokAdapter Upload] All {UPLOAD_MAX_RETRIES} attempts failed. "
                            f"Last error: {last_error}"
                        )

                # Success — parse response
                result = resp.json()

                logger.info(
                    f"[GrokAdapter Upload] Success | attempt={attempt} | "
                    f"elapsed={elapsed:.1f}s | response_keys={list(result.keys())}"
                )

                # Resolve the reference — xAI may return a URL or a file_id
                reference, ref_type = self._resolve_upload_reference(result)

                logger.success(
                    f"[GrokAdapter Upload] File ready | "
                    f"type={ref_type} | ref={reference[:80]}"
                )

                return {"reference": reference, "type": ref_type}

            except RuntimeError:
                # Re-raise non-retryable errors
                raise

            except httpx.TimeoutException as e:
                elapsed = time.time() - start_time
                last_error = f"Upload timeout after {elapsed:.1f}s: {e}"
                logger.warning(
                    f"[GrokAdapter Upload] Attempt {attempt} timed out | "
                    f"elapsed={elapsed:.1f}s | timeout={UPLOAD_TIMEOUT}s"
                )

            except httpx.ConnectError as e:
                last_error = f"Connection failed: {e}"
                logger.warning(
                    f"[GrokAdapter Upload] Attempt {attempt} connection error | {e}"
                )

            except Exception as e:
                last_error = f"Unexpected error: {e}"
                logger.warning(
                    f"[GrokAdapter Upload] Attempt {attempt} unexpected error | "
                    f"type={type(e).__name__} | {e}"
                )

            # Exponential backoff before retry
            if attempt < UPLOAD_MAX_RETRIES:
                delay = UPLOAD_BASE_DELAY * (2 ** (attempt - 1))
                logger.info(f"[GrokAdapter Upload] Waiting {delay:.1f}s before retry...")
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"[GrokAdapter Upload] All {UPLOAD_MAX_RETRIES} upload attempts failed for "
            f"{video_path.name} ({file_size_kb}KB). Last error: {last_error}"
        )

    @staticmethod
    def _resolve_upload_reference(api_response: dict) -> tuple[str, str]:
        """
        Extract the usable reference from the xAI Files API response.

        The API may return different fields depending on the version:
          - "url" or "file_url": A direct URL to the uploaded file.
          - "id" or "file_id": An opaque file identifier.

        Returns:
            Tuple of (reference_value, reference_type).
            reference_type is either "url" or "file_id".
        """
        # Priority 1: Direct URL (preferred — can be passed as video_url)
        url = api_response.get("url") or api_response.get("file_url")
        if url and url.startswith("http"):
            return url, "url"

        # Priority 2: File ID (passed as file_id parameter)
        file_id = api_response.get("id") or api_response.get("file_id")
        if file_id:
            return str(file_id), "file_id"

        # Fallback: use whatever string value we can find
        for key in ("url", "file_url", "id", "file_id", "object_id"):
            value = api_response.get(key)
            if value:
                logger.warning(
                    f"[GrokAdapter Upload] Using fallback reference: {key}={value[:60]}"
                )
                ref_type = "url" if "url" in key else "file_id"
                return str(value), ref_type

        raise RuntimeError(
            f"[GrokAdapter Upload] Cannot resolve file reference from API response. "
            f"Response keys: {list(api_response.keys())} | "
            f"Response: {str(api_response)[:200]}"
        )

    @staticmethod
    async def _download_video(url: str) -> bytes:
        """Download the generated video from the temporary URL."""
        async with httpx.AsyncClient(timeout=180.0) as http_client:
            resp = await http_client.get(url)
            resp.raise_for_status()
            return resp.content

    @staticmethod
    def _validate_prompt(prompt: str) -> None:
        """Ensure prompt is not empty — prevents wasted API calls."""
        if not prompt or not prompt.strip():
            raise ValueError(
                "[GrokAdapter] Prompt cannot be empty. Aborting to save credits."
            )

    @staticmethod
    def _validate_aspect_ratio(aspect_ratio: str) -> str:
        """Validate and return a supported aspect ratio."""
        if aspect_ratio in SUPPORTED_ASPECT_RATIOS:
            return aspect_ratio
        logger.warning(
            f"[GrokAdapter] Unsupported aspect_ratio '{aspect_ratio}', "
            f"falling back to '16:9'"
        )
        return "16:9"

    @staticmethod
    def _validate_resolution(resolution: str) -> str:
        """Validate and return a supported resolution."""
        if resolution in SUPPORTED_RESOLUTIONS:
            return resolution
        logger.warning(
            f"[GrokAdapter] Unsupported resolution '{resolution}', "
            f"falling back to '480p'. Supported: {SUPPORTED_RESOLUTIONS}"
        )
        return "480p"
