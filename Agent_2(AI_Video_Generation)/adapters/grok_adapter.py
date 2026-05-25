"""
xAI Grok Imagine Video adapter — Production-grade with animate + extend-video modes.

Three primary methods:
  1. generate_animated_clip() — Edit/animate the first clip (no prior context).
  2. extend_video() — Continue from previous clip's last frame (seamless).
  3. generate_edit_video() — Legacy edit-video mode (still available).

All methods include robust upload with 3-attempt retry and exponential backoff.
"""

import asyncio
import mimetypes
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

UPLOAD_MAX_RETRIES = 3
UPLOAD_BASE_DELAY = 2.0
UPLOAD_TIMEOUT = 120.0
XAI_FILES_API_URL = "https://api.x.ai/v1/files"

EDIT_VIDEO_PREFIX = (
    "Enhance this real screen recording. Keep every UI element, text, button, "
    "icon, and layout 100% identical to the original video. "
)


class GrokAdapter(VideoGenerationService):
    """
    xAI Grok Imagine Video adapter.

    Supports:
      - generate_animated_clip(): First clip — animate/edit mode.
      - extend_video(): Subsequent clips — extend from previous for continuity.
      - generate_edit_video(): General edit-video mode.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    # ─── Public API: Animate (First Clip) ─────────────────────────────────────

    async def generate_animated_clip(
        self,
        input_video_path: str,
        prompt: str,
        duration: int = 8,
        output_path: Path | None = None,
        aspect_ratio: str = "16:9",
        resolution: str = "480p",
    ) -> dict[str, Any]:
        """
        Animate/enhance the first clip using edit-video mode.

        Used for clip 0 — the starting point. No previous clip context needed.
        """
        video_file = Path(input_video_path)
        if not video_file.exists():
            raise FileNotFoundError(f"Input video not found: {input_video_path}")

        if output_path is None:
            output_path = video_file.with_suffix(".animated.mp4")

        clamped_duration = max(1, min(duration, settings.max_clip_duration))

        logger.info(
            f"[GrokAdapter] ANIMATE clip | input={video_file.name} | "
            f"duration={clamped_duration}s"
        )

        if settings.dry_run:
            return self._dry_run_result(output_path, video_file, "animate", clamped_duration)

        # Upload input video
        upload_result = await self._upload_video_file(video_file)

        # Call API in edit-video mode (animate = edit-video without prior context)
        gen_kwargs = self._build_gen_kwargs(
            prompt=EDIT_VIDEO_PREFIX + prompt,
            duration=clamped_duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            upload_result=upload_result,
            mode="edit-video",
        )

        return await self._execute_and_save(gen_kwargs, output_path, video_file, "animate")

    # ─── Public API: Extend Video (Subsequent Clips) ──────────────────────────

    async def extend_video(
        self,
        previous_video_path: str | None,
        input_video_path: str,
        prompt: str,
        duration: int = 8,
        output_path: Path | None = None,
        aspect_ratio: str = "16:9",
        resolution: str = "480p",
    ) -> dict[str, Any]:
        """
        Extend from the previous clip for seamless continuity.

        Uses extend-video mode: the API continues generation from the last frame
        of the previous clip, ensuring no visual jumps between segments.

        Args:
            previous_video_path: Path to the previously generated clip (for continuity).
            input_video_path: Path to the current raw clip (reference for content).
            prompt: Continuity prompt with strong anti-hallucination constraints.
            duration: Target duration in seconds.
            output_path: Where to save the result.
        """
        video_file = Path(input_video_path)
        if not video_file.exists():
            raise FileNotFoundError(f"Input video not found: {input_video_path}")

        if output_path is None:
            output_path = video_file.with_suffix(".extended.mp4")

        clamped_duration = max(1, min(duration, settings.max_clip_duration))

        logger.info(
            f"[GrokAdapter] EXTEND-VIDEO clip | input={video_file.name} | "
            f"previous={Path(previous_video_path).name if previous_video_path else 'none'} | "
            f"duration={clamped_duration}s"
        )

        if settings.dry_run:
            return self._dry_run_result(output_path, video_file, "extend-video", clamped_duration)

        # Upload the previous clip (source for extend-video continuity)
        prev_file = Path(previous_video_path) if previous_video_path else video_file
        if not prev_file.exists():
            prev_file = video_file

        upload_result = await self._upload_video_file(prev_file)

        # Call API in extend-video mode
        gen_kwargs = self._build_gen_kwargs(
            prompt=prompt,
            duration=clamped_duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            upload_result=upload_result,
            mode="extend-video",
        )

        return await self._execute_and_save(gen_kwargs, output_path, video_file, "extend-video")

    # ─── Public API: General Edit-Video ───────────────────────────────────────

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
        """General edit-video mode (backward compatible)."""
        video_file = Path(input_video_path)
        if not video_file.exists():
            raise FileNotFoundError(f"Input video not found: {input_video_path}")

        if output_path is None:
            output_path = video_file.with_suffix(".enhanced.mp4")

        clamped_duration = max(1, min(duration, settings.max_clip_duration))

        if dry_run or settings.dry_run:
            return self._dry_run_result(output_path, video_file, "edit-video", clamped_duration)

        upload_result = await self._upload_video_file(video_file)

        gen_kwargs = self._build_gen_kwargs(
            prompt=EDIT_VIDEO_PREFIX + prompt,
            duration=clamped_duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            upload_result=upload_result,
            mode="edit-video",
        )

        return await self._execute_and_save(gen_kwargs, output_path, video_file, "edit-video")

    # ─── Abstract interface implementation ────────────────────────────────────

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
        """Base interface — delegates to generate_edit_video for compatibility."""
        return await self.generate_edit_video(
            input_video_path=str(output_path),
            prompt=prompt,
            duration=duration,
            output_path=output_path,
            dry_run=dry_run,
        )

    # ─── Internal Helpers ─────────────────────────────────────────────────────

    def _build_gen_kwargs(
        self,
        prompt: str,
        duration: int,
        aspect_ratio: str,
        resolution: str,
        upload_result: dict[str, str],
        mode: str,
    ) -> dict[str, Any]:
        """Build the kwargs dict for the xAI SDK call."""
        validated_ar = aspect_ratio if aspect_ratio in SUPPORTED_ASPECT_RATIOS else "16:9"
        validated_res = resolution if resolution in SUPPORTED_RESOLUTIONS else "480p"

        gen_kwargs: dict[str, Any] = {
            "model": "grok-imagine-video",
            "prompt": prompt,
            "mode": mode,
            "duration": duration,
            "aspect_ratio": validated_ar,
            "resolution": validated_res,
        }

        reference = upload_result["reference"]
        ref_type = upload_result["type"]

        if ref_type == "url":
            gen_kwargs["video_url"] = reference
        else:
            gen_kwargs["file_id"] = reference

        return gen_kwargs

    async def _execute_and_save(
        self,
        gen_kwargs: dict[str, Any],
        output_path: Path,
        input_file: Path,
        mode: str,
    ) -> dict[str, Any]:
        """Execute the xAI SDK call and save the result."""
        logger.info(f"[GrokAdapter] Calling API | mode={mode}")

        client = Client(api_key=self._api_key)
        response = client.video.generate(**gen_kwargs)

        result_url = response.url
        video_bytes = await self._download_video(result_url)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(video_bytes)

        response_duration = getattr(response, "duration", gen_kwargs.get("duration", 8))

        logger.success(
            f"[GrokAdapter] Saved: {output_path.name} | "
            f"mode={mode} | duration={response_duration}s | "
            f"size={output_path.stat().st_size // 1024}KB"
        )

        return {
            "status": "success",
            "path": str(output_path),
            "model": "grok-imagine-video",
            "duration": response_duration,
            "provider": "xai",
            "mode": mode,
            "input_video": str(input_file),
            "video_url": result_url,
            "cost_usd": getattr(response, "cost_usd", None),
        }

    def _dry_run_result(self, output_path: Path, input_file: Path, mode: str, duration: int) -> dict:
        """Return a dry-run result without calling the API."""
        logger.warning(f"[GrokAdapter] DRY RUN | mode={mode} | input={input_file.name}")
        return {
            "status": "dry_run",
            "path": str(output_path),
            "model": "grok-imagine-video",
            "duration": duration,
            "provider": "xai",
            "mode": mode,
            "input_video": str(input_file),
            "video_url": None,
            "cost_usd": 0.0,
        }

    # ─── Upload with Retry ────────────────────────────────────────────────────

    async def _upload_video_file(self, video_path: Path) -> dict[str, str]:
        """Upload video to xAI Files API with 3-attempt retry."""
        mime_type = mimetypes.guess_type(str(video_path))[0] or "video/mp4"
        file_size_kb = video_path.stat().st_size // 1024

        logger.info(f"[Upload] {video_path.name} ({file_size_kb}KB)")

        last_error = ""

        for attempt in range(1, UPLOAD_MAX_RETRIES + 1):
            start_time = time.time()
            try:
                async with httpx.AsyncClient(timeout=UPLOAD_TIMEOUT) as http_client:
                    headers = {"Authorization": f"Bearer {self._api_key}"}

                    with open(video_path, "rb") as f:
                        files = {
                            "file": (video_path.name, f, mime_type),
                            "purpose": (None, "video-edit"),
                        }
                        resp = await http_client.post(
                            XAI_FILES_API_URL, headers=headers, files=files,
                        )

                elapsed = time.time() - start_time

                if resp.status_code >= 400:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    logger.warning(f"[Upload] Attempt {attempt} failed: {last_error}")

                    if 400 <= resp.status_code < 500 and resp.status_code != 429:
                        raise RuntimeError(f"Upload client error: {last_error}")

                    if attempt < UPLOAD_MAX_RETRIES:
                        delay = UPLOAD_BASE_DELAY * (2 ** (attempt - 1))
                        await asyncio.sleep(delay)
                        continue
                    raise RuntimeError(f"Upload failed after {UPLOAD_MAX_RETRIES} attempts: {last_error}")

                result = resp.json()
                reference, ref_type = self._resolve_upload_reference(result)
                logger.info(f"[Upload] Success in {elapsed:.1f}s | {ref_type}={reference[:60]}")
                return {"reference": reference, "type": ref_type}

            except RuntimeError:
                raise
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[Upload] Attempt {attempt} error: {last_error}")
                if attempt < UPLOAD_MAX_RETRIES:
                    await asyncio.sleep(UPLOAD_BASE_DELAY * (2 ** (attempt - 1)))

        raise RuntimeError(f"Upload failed for {video_path.name}: {last_error}")

    @staticmethod
    def _resolve_upload_reference(api_response: dict) -> tuple[str, str]:
        """Extract URL or file_id from upload response."""
        url = api_response.get("url") or api_response.get("file_url")
        if url and url.startswith("http"):
            return url, "url"

        file_id = api_response.get("id") or api_response.get("file_id")
        if file_id:
            return str(file_id), "file_id"

        for key in ("url", "file_url", "id", "file_id", "object_id"):
            value = api_response.get(key)
            if value:
                return str(value), "url" if "url" in key else "file_id"

        raise RuntimeError(f"Cannot resolve reference from: {list(api_response.keys())}")

    @staticmethod
    async def _download_video(url: str) -> bytes:
        """Download generated video from temporary URL."""
        async with httpx.AsyncClient(timeout=180.0) as http_client:
            resp = await http_client.get(url)
            resp.raise_for_status()
            return resp.content
