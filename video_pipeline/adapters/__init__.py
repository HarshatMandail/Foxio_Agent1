"""
Adapter factory — returns the xAI Grok Imagine Video adapter instance.
"""

from adapters.base import VideoGenerationService
from adapters.grok_adapter import GrokAdapter
from config.settings import settings


def get_adapter() -> VideoGenerationService:
    """Return the xAI Grok Imagine Video adapter instance."""
    return GrokAdapter(api_key=settings.xai_api_key)


__all__ = ["get_adapter", "VideoGenerationService", "GrokAdapter"]
