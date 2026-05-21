"""Foxio — Multi-Agent Platform Analyzer + Video Generator.

Agent 1: Browser automation + Azure OpenAI → structured platform analysis.
Agent 2: LLM prompt engineering → text-to-video generation pipeline.
Pipeline: Agent 1 → Agent 2 unified flow.
"""

from .agent import run_agent1
from .agent2 import run_agent2, generate_video_prompts
from .browser_pool import shutdown_browser_pool
from .config import validate_config, validate_url
from .cost_tracker import get_session, reset_session
from .graph import create_agent1_graph
from .llm import get_azure_client, analyze_with_llm
from .models import Agent1Output, PageContext, UIElement, PageCapture
from .navigation_planner import plan_navigation
from .pipeline import run_full_pipeline
from .state import AgentState

__all__ = [
    "run_full_pipeline",
    "run_agent1",
    "run_agent2",
    "generate_video_prompts",
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
]
