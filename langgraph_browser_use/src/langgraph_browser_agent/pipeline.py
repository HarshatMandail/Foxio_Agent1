# pipeline.py — Unified Foxio Pipeline: Agent 1 (Browser Analysis) → Agent 2 (Video Generation)

import logging
from typing import Any

from .agent import run_agent1
from .agent2 import run_agent2
from .models import Agent1Output

logger = logging.getLogger(__name__)


async def run_full_pipeline(
    url: str,
    user_query: str,
    dry_run: bool = True,
    cleanup_browser: bool = False,
) -> dict[str, Any]:
    """
    Execute the complete Foxio pipeline:
      Agent 1: Navigate platform → capture pages → analyze with LLM → structured output
      Agent 2: Transform output → generate video prompts → produce tutorial video

    Args:
        url: Platform URL to analyze.
        user_query: User's question (e.g., "How do I create a contract?").
        dry_run: If True, skip actual video API calls (saves credits).
        cleanup_browser: If True, close browser after Agent 1 finishes.

    Returns:
        Dict with agent1_output, agent2_output, and overall status.
    """
    logger.info("=" * 60)
    logger.info("FOXIO PIPELINE — Agent 1 → Agent 2")
    logger.info(f"URL: {url}")
    logger.info(f"Query: {user_query}")
    logger.info(f"Dry Run: {dry_run}")
    logger.info("=" * 60)

    # ─── Agent 1: Browser Analysis ────────────────────────────────────────────
    logger.info("[Pipeline] Running Agent 1: Platform Analysis...")

    try:
        agent1_output: Agent1Output = await run_agent1(
            url=url,
            user_query=user_query,
            cleanup_browser=cleanup_browser,
        )
    except Exception as e:
        logger.error(f"[Pipeline] Agent 1 failed: {e}")
        return {
            "status": "failed",
            "stage": "agent1",
            "error": str(e),
            "agent1_output": None,
            "agent2_output": None,
        }

    logger.info(
        f"[Pipeline] Agent 1 complete | "
        f"Platform: {agent1_output.platform_name} | "
        f"Pages: {len(agent1_output.pages_captured)}"
    )

    # ─── Agent 2: Video Generation ────────────────────────────────────────────
    logger.info("[Pipeline] Running Agent 2: Video Generation...")

    agent1_dict = agent1_output.model_dump()

    try:
        agent2_output = await run_agent2(
            agent1_output=agent1_dict,
            user_query=user_query,
            dry_run=dry_run,
        )
    except Exception as e:
        logger.error(f"[Pipeline] Agent 2 failed: {e}")
        return {
            "status": "partial",
            "stage": "agent2_failed",
            "error": str(e),
            "agent1_output": agent1_dict,
            "agent2_output": None,
        }

    logger.info(
        f"[Pipeline] Agent 2 complete | "
        f"Status: {agent2_output.get('status')} | "
        f"Title: {agent2_output.get('video_title', 'N/A')}"
    )

    # ─── Final Result ─────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("[Pipeline] FULL PIPELINE COMPLETE")
    logger.info("=" * 60)

    return {
        "status": "completed",
        "stage": "done",
        "agent1_output": agent1_dict,
        "agent2_output": agent2_output,
    }
