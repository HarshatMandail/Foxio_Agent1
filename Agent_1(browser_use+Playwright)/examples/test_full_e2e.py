"""
Full End-to-End Pipeline Test: Agent 1 (Browser) → Agent 2 (Edit-Video)

This script:
  1. Runs Agent 1 to navigate a platform and record real video clips
  2. Feeds those video_clips directly into the Edit-Video pipeline
  3. Produces a final polished tutorial video

Usage:
    cd Agent_1(browser_use+Playwright)
    python examples/test_full_e2e.py

Set DRY_RUN=true in Agent_2/.env to skip real xAI API calls during testing.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Resolve project roots
_THIS_DIR = Path(__file__).resolve().parent
_AGENT1_ROOT = _THIS_DIR.parent
_AGENT2_ROOT = _AGENT1_ROOT.parent / "Agent_2(AI_Video_Generation)"

# Add Agent 1 src and Agent 2 to path
sys.path.insert(0, str(_AGENT1_ROOT / "src"))
sys.path.insert(0, str(_AGENT2_ROOT))

from dotenv import load_dotenv

load_dotenv(dotenv_path=_AGENT1_ROOT / ".env")
load_dotenv(dotenv_path=_AGENT2_ROOT / ".env")


async def main():
    """Run the full pipeline: Browser Agent → Edit-Video Pipeline."""

    URL = "https://login.salesforce.com"
    USER_QUERY = "How do I create a new contact in Salesforce?"

    print("=" * 70)
    print("FULL E2E PIPELINE: Agent 1 (Browser) → Agent 2 (Edit-Video)")
    print(f"URL: {URL}")
    print(f"Query: {USER_QUERY}")
    print("=" * 70)

    # ─── Step 1: Run Agent 1 ──────────────────────────────────────────────────
    print("\n[1/3] Running Agent 1: Browser navigation + video recording...")

    from langgraph_browser_agent.agent import run_agent1

    try:
        agent1_output = await run_agent1(
            url=URL,
            user_query=USER_QUERY,
            cleanup_browser=True,
        )
    except Exception as e:
        print(f"\n✗ Agent 1 failed: {e}")
        return

    print(f"\n✓ Agent 1 complete!")
    print(f"  Platform: {agent1_output.platform_name}")
    print(f"  Pages captured: {len(agent1_output.pages_captured)}")
    print(f"  Video clips: {len(agent1_output.video_clips)}")

    for clip in agent1_output.video_clips:
        print(f"    Step {clip['step']}: {clip['narration'][:60]}")
        print(f"      Video: {clip['video_path']}")

    # ─── Step 2: Feed video_clips to Edit-Video Pipeline ──────────────────────
    video_clips = agent1_output.video_clips

    if not video_clips:
        print("\n⚠ No video clips recorded by Agent 1. Cannot proceed to Agent 2.")
        print("  This can happen if the workflow had no navigation steps.")
        return

    print(f"\n[2/3] Running Agent 2: Edit-Video pipeline ({len(video_clips)} clips)...")

    from graph.workflow import run_pipeline

    result = await run_pipeline(
        video_clips=video_clips,
        job_id=None,
    )

    # ─── Step 3: Print Results ────────────────────────────────────────────────
    print(f"\n[3/3] Results:")
    print("=" * 70)
    print(f"  Status: {result.get('status')}")
    print(f"  Job ID: {result.get('job_id')}")
    print(f"  Final Video: {result.get('final_video_path', 'none')}")
    print(f"  Error: {result.get('error') or 'none'}")

    clip_results = result.get("clip_results", [])
    if clip_results:
        success = sum(1 for c in clip_results if c["status"] in ("success", "dry_run"))
        failed = sum(1 for c in clip_results if c["status"] == "failed")
        print(f"  Clips: {success} success, {failed} failed")

    print("=" * 70)

    if result.get("status") == "completed":
        final_path = result.get("final_video_path", "")
        if final_path and final_path != "dry_run_no_output":
            print(f"\n✓ Tutorial video saved: {final_path}")
        else:
            print("\n✓ Pipeline completed (dry-run mode — no video file produced)")
    else:
        print(f"\n✗ Pipeline failed: {result.get('error')}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    asyncio.run(main())
