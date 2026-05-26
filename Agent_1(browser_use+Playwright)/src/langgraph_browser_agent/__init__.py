"""Foxio — Multi-Agent Platform Analyzer + Video Generator.

Agent 1: Browser automation + Azure OpenAI → structured platform analysis + video recording.
Agent 2: Edit-Video pipeline → polished tutorial video from real recordings.
Pipeline: Agent 1 → Agent 2 unified flow.
"""

from .agent import run_agent1
from .browser_pool import shutdown_browser_pool
from .config import validate_config, validate_url, OUTPUT_DIR
from .cost_tracker import get_session, reset_session
from .graph import create_agent1_graph
from .llm import get_azure_client, analyze_with_llm
from .models import Agent1Output, PageContext, UIElement, PageCapture
from .navigation_planner import plan_navigation
from .pipeline import run_full_pipeline
from .state import AgentState
from .video_merger import merge_all_recordings, convert_clips_to_mp4, clean_old_clips

__all__ = [
    "run_full_pipeline",
    "run_agent1",
    "plan_navigation",
    "shutdown_browser_pool",
    "Agent1Output",
    "PageContext",
    "UIElement",
    "PageCapture",
    "AgentState",
    "create_agent1_graph",
    "get_azure_client",
    "analyze_with_llm",
    "get_session",
    "reset_session",
    "validate_config",
    "validate_url",
    "merge_all_recordings",
    "convert_clips_to_mp4",
    "OUTPUT_DIR",
]
