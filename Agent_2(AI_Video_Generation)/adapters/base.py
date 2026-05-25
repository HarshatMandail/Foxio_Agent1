"""
Abstract base class for video generation adapters.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from core.registry import VideoModel


class VideoGenerationService(ABC):
    """Abstract interface for video generation."""

    @abstractmethod
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
        Generate a video clip and save it to output_path.

        Args:
            model: The VideoModel definition from the registry.
            prompt: Text prompt describing the video content.
            duration: Clip duration in seconds (1-10).
            output_path: Where to save the generated clip.
            aspect_ratio: Video aspect ratio ("16:9", "9:16", "1:1").
            resolution: Video resolution ("480p" or "720p").
            start_image: Optional URL for image-to-video.
            dry_run: If True, skip API call and log only.

        Returns:
            Dict with generation metadata.
        """
        ...
