"""
Example: How to call Agent 1 from your backend.
Use this file to test Agent 1.
"""

import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

from langgraph_browser_agent.agent import run_agent1
from langgraph_browser_agent.cost_tracker import get_session


async def main():
    result = await run_agent1(
        url="https://login.salesforce.com/",
        user_query="How do I create a new contract or opportunity?",
    )

    print("\n" + "=" * 60)
    print("[OK] Agent 1 Execution Completed!")
    print("=" * 60)

    print(f"\nPlatform Name     : {result.platform_name}")
    print(f"Pages Captured    : {len(result.pages_captured)}")
    print(f"Page Title        : {result.current_page.title}")
    print(f"Overall Journey   : {result.overall_user_journey}")

    print("\n[Screenshots]")
    for cap in result.pages_captured:
        print(f"  - {cap.screenshot_path}")

    print("\n[Relevant Workflows]")
    for i, step in enumerate(result.relevant_workflows, 1):
        print(f"  {i}. {step}")

    print("\n[Context For Video Generation]")
    ctx = result.context_for_video
    print(ctx[:500] + "..." if len(ctx) > 500 else ctx)

    # Print cost summary
    session = get_session()
    summary = session.get_summary()
    print(f"\n[Cost Summary]")
    print(f"  LLM Calls    : {summary['call_count']}")
    print(f"  Cache Hits   : {summary['cache_hits']}")
    print(f"  Total Tokens : {summary['total_tokens']}")
    print(f"  Total Cost   : ${summary['total_cost_usd']}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    asyncio.run(main())
