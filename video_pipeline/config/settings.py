"""
Application settings loaded from environment variables.
Uses pydantic-settings for validation and type coercion.

Resolves .env relative to THIS file's directory so it works
regardless of which working directory the process runs from.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env path relative to video_pipeline/ root (one level up from config/)
_VIDEO_PIPELINE_DIR = Path(__file__).resolve().parent.parent
_ENV_FILE = _VIDEO_PIPELINE_DIR / ".env"
_PROJECT_ROOT = _VIDEO_PIPELINE_DIR.parent / "langgraph_browser_use"
_GENERATED_VIDEOS_DIR = _PROJECT_ROOT / "generated_videos"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # xAI API Key (required for video generation)
    xai_api_key: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Video pipeline
    default_model: str = "grok-imagine-video"
    default_resolution: str = "480p"
    max_retries: int = 3
    retry_base_delay: float = 2.0
    clip_output_dir: Path = _GENERATED_VIDEOS_DIR / "clips"
    final_output_dir: Path = _GENERATED_VIDEOS_DIR
    max_clip_duration: int = 10
    log_level: str = "INFO"

    # Dry run mode — logs prompts without making API calls (saves credits)
    dry_run: bool = False

    # xAI SDK settings
    sdk_generation_timeout: int = 600
    sdk_poll_interval: float = 1.0

    # Tutorial / CLM-specific settings
    min_tutorial_steps: int = 4
    max_tutorial_steps: int = 8
    default_clip_duration: int = 6
    tutorial_aspect_ratio: str = "16:9"
    prompt_style: str = "beginner_friendly"


settings = Settings()
