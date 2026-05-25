# examples/run_full_pipeline.py — Run the complete Foxio pipeline (Agent 1 → Agent 2)

import asyncio
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from langgraph_browser_agent import run_full_pipeline, shutdown_browser_pool


async def main():
    """Run the full Foxio pipeline: Browser Analysis → Video Generation."""
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

    if result.get("agent2_output"):
        a2 = result["agent2_output"]
        print(f"\nVideo Title: {a2.get('video_title', 'N/A')}")
        print(f"Video Clips: {len(a2.get('video_prompts', []))}")

        print("\n--- Generated Video Prompts ---")
        for step in a2.get("video_prompts", []):
            print(f"\n  Step {step.get('step_number', '?')} ({step.get('duration', 6)}s):")
            print(f"    {step.get('prompt', '')[:120]}...")

        if a2.get("pipeline_result"):
            pr = a2["pipeline_result"]
            print(f"\nPipeline Status: {pr.get('status')}")
            print(f"Job ID: {pr.get('job_id')}")
            print(f"Final Video: {pr.get('final_video_path', 'N/A')}")

    if result.get("error"):
        print(f"\nError: {result['error']}")


if __name__ == "__main__":
    asyncio.run(main())
