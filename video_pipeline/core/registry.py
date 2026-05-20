"""
Model Registry — single-provider model definitions for xAI Grok Imagine Video.
"""

from dataclasses import dataclass, field
from typing import Any

from loguru import logger


@dataclass(frozen=True)
class VideoModel:
    """Represents a registered video generation model."""

    name: str
    provider: str = "xai"
    default_params: dict[str, Any] = field(default_factory=dict)
    max_duration: int = 10
    supports_image_to_video: bool = True
    supports_video_editing: bool = True
    supports_reference_images: bool = True


class ModelRegistry:
    """Central registry for video generation models."""

    def __init__(self) -> None:
        self._models: dict[str, VideoModel] = {}

    def register(self, model: VideoModel) -> None:
        self._models[model.name] = model
        logger.info(f"Registered model: {model.name} (provider={model.provider})")

    def get(self, name: str) -> VideoModel:
        if name not in self._models:
            available = list(self._models.keys())
            raise ValueError(f"Model '{name}' not found. Available: {available}")
        return self._models[name]

    def list_models(self) -> list[str]:
        return list(self._models.keys())


# Singleton registry instance
model_registry = ModelRegistry()

# Register the xAI Grok Imagine Video model
model_registry.register(
    VideoModel(
        name="grok-imagine-video",
        provider="xai",
        default_params={
            "aspect_ratio": "16:9",
            "resolution": "720p",
        },
        max_duration=10,
        supports_image_to_video=True,
        supports_video_editing=True,
        supports_reference_images=True,
    )
)
