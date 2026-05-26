"""
Abstract base class for video generation adapters.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class VideoGenerationService(ABC):
    """Abstract interface for video generation adapters."""

    @abstractmethod
    async def generate_animated_clip(
        self,
        input_video_path: str,
        prompt: str,
        duration: int = 8,
        output_path: Path | None = None,
        aspect_ratio: str = "16:9",
        resolution: str = "480p",
    ) -> dict[str, Any]:
        """Animate/enhance a clip (first clip, no prior context)."""
        ...

    @abstractmethod
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
        """Extend from previous clip for seamless continuity."""
        ...
