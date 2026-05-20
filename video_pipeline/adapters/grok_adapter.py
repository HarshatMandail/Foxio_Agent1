"""
xAI Grok Imagine Video adapter — Official SDK implementation.

Uses `xai_sdk.Client` for video generation.
API: client.video.generate(prompt, model, duration, aspect_ratio, resolution, image_url)
Response: response.url, response.duration

Supports:
  - Text-to-video (prompt only)
  - Image-to-video (prompt + image_url as first frame)
"""

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


class GrokAdapter(VideoGenerationService):
    """
    Official xAI SDK adapter for Grok Imagine Video.

    Uses the synchronous Client from xai-sdk package.
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
        Generate a video using the official xAI SDK.

        Args:
            model: VideoModel from registry.
            prompt: Text prompt for video generation.
            duration: Clip duration in seconds (1-10).
            output_path: File path to save the downloaded video.
            aspect_ratio: "16:9", "9:16", or "1:1".
            resolution: "480p" or "720p".
            start_image: Optional image URL for image-to-video.
            dry_run: If True, log the request without calling the API.

        Returns:
            Dict with generation metadata.
        """
        self._validate_prompt(prompt)
        validated_aspect_ratio = self._validate_aspect_ratio(aspect_ratio)
        validated_resolution = self._validate_resolution(resolution)
        clamped_duration = max(1, min(duration, settings.max_clip_duration))

        logger.info(
            f"[GrokAdapter] Requesting video | model={model.name} | "
            f"duration={clamped_duration}s | "
            f"aspect_ratio={validated_aspect_ratio} | "
            f"resolution={validated_resolution}"
        )

        if dry_run or settings.dry_run:
            logger.warning(
                f"[GrokAdapter] DRY RUN — skipping API call. "
                f"Prompt: {prompt[:100]}..."
            )
            return {
                "status": "dry_run",
                "path": str(output_path),
                "model": model.name,
                "duration": clamped_duration,
                "provider": "xai",
                "video_url": None,
                "cost_usd": 0.0,
            }

        # Build generation kwargs
        gen_kwargs: dict[str, Any] = {
            "prompt": prompt,
            "model": model.name,
            "duration": clamped_duration,
            "aspect_ratio": validated_aspect_ratio,
            "resolution": validated_resolution,
        }

        if start_image:
            gen_kwargs["image_url"] = start_image

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
            f"duration={response_duration}s"
        )

        return {
            "status": "success",
            "path": str(output_path),
            "model": model.name,
            "duration": response_duration,
            "provider": "xai",
            "video_url": video_url,
            "cost_usd": getattr(response, "cost_usd", None),
        }

    @staticmethod
    async def _download_video(url: str) -> bytes:
        """Download the generated video from the temporary URL."""
        async with httpx.AsyncClient(timeout=120.0) as http_client:
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
