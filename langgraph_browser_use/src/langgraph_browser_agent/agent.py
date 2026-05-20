# agent.py — Main Entry Point with Tracing & Lifecycle Management
import logging

from .browser_pool import shutdown_browser_pool
from .config import validate_config, ENABLE_LANGSMITH, LANGSMITH_PROJECT
from .graph import create_agent1_graph
from .logger import setup_logging
from .models import Agent1Output
from .state import AgentState

logger = logging.getLogger(__name__)

# Initialize logging on import
setup_logging()


async def run_agent1(
    url: str,
    user_query: str,
    cleanup_browser: bool = False,
) -> Agent1Output:
    """
    Main entry point for Agent 1.

    Args:
        url: The platform URL to analyze (e.g., Salesforce login page).
        user_query: The user's question (e.g., "How do I create a new contract?")
        cleanup_browser: If True, close browser pool after run (for one-shot usage).

    Returns:
        Agent1Output: Full platform analysis with multi-page context for video generation.

    Raises:
        ValueError: If configuration is invalid.
    """
    # Validate config
    errors = validate_config()
    if errors:
        raise ValueError(f"Configuration errors: {'; '.join(errors)}")

    # LangSmith tracing (if enabled via LANGCHAIN_TRACING_V2=true)
    config = {}
    if ENABLE_LANGSMITH:
        config["metadata"] = {"project": LANGSMITH_PROJECT, "url": url[:100]}
        logger.info(f"LangSmith tracing enabled (project: {LANGSMITH_PROJECT})")

    graph = create_agent1_graph()

    initial_state: AgentState = {
        "url": url,
        "user_query": user_query,
        "page_captures": None,
        "structured_output": None,
    }

    try:
        final_state = await graph.ainvoke(initial_state, config=config)
        return final_state["structured_output"]
    finally:
        if cleanup_browser:
            await shutdown_browser_pool()
