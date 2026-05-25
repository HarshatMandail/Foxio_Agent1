# examples/run_full_pipeline.py — Run the complete Foxio pipeline (Agent 1 → Agent 2)

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from langgraph_browser_agent import run_full_pipeline, shutdown_browser_pool


async def main():
    """Run the full Foxio pipeline: Browser Analysis + Recording → Edit-Video."""
    url = "https://login.salesforce.com"
    user_query = "How do I create a first contact for growing your sales in Salesforce?"

    print("=" * 60)
    print("FOXIO — Full Pipeline (Agent 1 → Agent 2)")
    print(f"URL: {url}")
    print(f"Query: {user_query}")
    print("=" * 60)

    result = await run_full_pipeline(
        url=url,
        user_query=user_query,
        cleanup_browser=True,
    )

    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    print(f"Status: {result['status']}")
    print(f"Stage: {result.get('stage', 'N/A')}")

    if result.get("video_result"):
        vr = result["video_result"]
        print(f"\nVideo Title: {vr.get('video_title', 'N/A')}")
        print(f"Job ID: {vr.get('job_id', 'N/A')}")
        print(f"Final Video: {vr.get('final_video_path', 'N/A')}")
        print(f"Clips: {vr.get('steps_generated', 0)}")

    if result.get("error"):
        print(f"\nError: {result['error']}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    asyncio.run(main())
