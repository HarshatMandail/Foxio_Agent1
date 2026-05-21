# navigation_planner.py — LLM-Driven Navigation Planner
# Decides which pages to visit based on user query + current page DOM

import json
import logging
from typing import Any

from .llm import analyze_with_llm

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """\
You are a navigation planner for a SaaS platform tutorial system.

Given the user's question and the current page DOM data, decide what navigation steps are needed to capture the full workflow.

## Rules:
1. If the user's question can be answered from the CURRENT page alone (e.g., "what is this page?"), return an empty steps array.
2. If the task requires navigating to other pages (e.g., "how to create a contract"), plan the navigation steps.
3. Each step should describe ONE click/navigation action with a CSS selector or link text to find the element.
4. Maximum 6 navigation steps — keep it focused.
5. Use the DOM data (navigation links, buttons) to identify REAL elements that exist on the page.
6. Prefer clicking navigation links/buttons over typing URLs.
7. If a step requires opening a form (like "New"), include that as a step.

## Output Format (strict JSON):
{
  "needs_navigation": true/false,
  "reasoning": "Brief explanation of why navigation is/isn't needed",
  "steps": [
    {
      "action": "click_nav" | "click_button" | "goto_url",
      "target": "exact text of link/button to click OR url to navigate to",
      "description": "What this step does (e.g., 'Navigate to Contracts list')",
      "wait_after": 2
    }
  ]
}
"""


def _build_planner_input(
    user_query: str,
    page_title: str,
    page_url: str,
    dom_summary: dict,
) -> str:
    nav_links = dom_summary.get("navigation", [])
    buttons = dom_summary.get("buttons", [])
    visible_text = dom_summary.get("visible_text", "")[:500]

    return (
        f"## User Query\n\"{user_query}\"\n\n"
        f"## Current Page\n"
        f"Title: {page_title}\n"
        f"URL: {page_url}\n\n"
        f"## Available Navigation Links\n"
        f"{json.dumps(nav_links[:25], default=str)}\n\n"
        f"## Available Buttons\n"
        f"{json.dumps(buttons[:20], default=str)}\n\n"
        f"## Visible Text (first 500 chars)\n"
        f"{visible_text}\n\n"
        f"## Instructions\n"
        f"Based on the user's question and what's available on this page, "
        f"plan the navigation steps needed to capture the full workflow. "
        f"If the current page already has everything needed, return needs_navigation=false."
    )


async def plan_navigation(
    user_query: str,
    page_title: str,
    page_url: str,
    dom_summary: dict,
) -> dict[str, Any]:
    """
    Ask the LLM to plan navigation steps based on user query and current page.

    Returns:
        Dict with needs_navigation, reasoning, and steps array.
    """
    user_message = _build_planner_input(user_query, page_title, page_url, dom_summary)

    logger.info("Navigation Planner: Analyzing page for required navigation...")

    raw = await analyze_with_llm(
        system_prompt=PLANNER_SYSTEM_PROMPT,
        user_message=user_message,
        use_mini=True,
    )

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Navigation Planner: Failed to parse LLM response, defaulting to no navigation")
        return {"needs_navigation": False, "reasoning": "Parse error", "steps": []}

    needs_nav = result.get("needs_navigation", False)
    steps = result.get("steps", [])

    logger.info(
        f"Navigation Planner: needs_navigation={needs_nav} | "
        f"steps={len(steps)} | reason={result.get('reasoning', '')[:80]}"
    )

    return result
