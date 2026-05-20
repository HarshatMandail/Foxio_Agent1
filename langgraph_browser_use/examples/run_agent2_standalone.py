# examples/run_agent2_standalone.py — Run Agent 2 with pre-existing Agent 1 output

import asyncio
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from langgraph_browser_agent import run_agent2


# Sample Agent1Output (simulating what Agent 1 would produce)
SAMPLE_AGENT1_OUTPUT = {
    "platform_name": "Salesforce",
    "current_page": {
        "url": "https://myorg.lightning.force.com/lightning/o/Contract/list",
        "title": "Recently Viewed | Contracts | Salesforce",
        "description": "The Contracts list view showing all recently viewed contracts with columns for Contract Number, Account Name, Status, and Start Date.",
        "key_elements": [
            {
                "element_type": "button",
                "visible_text": "New",
                "purpose": "Create a new contract",
                "suggested_action": "Click to open the new contract form",
            },
            {
                "element_type": "list_view",
                "visible_text": "Recently Viewed",
                "purpose": "Display recent contracts",
                "suggested_action": "Browse existing contracts",
            },
        ],
        "main_actions": [
            "Create new contract",
            "Edit existing contract",
            "Change list view",
            "Search contracts",
        ],
    },
    "overall_user_journey": "User navigates to Contracts tab → clicks New → fills contract details → saves the contract.",
    "relevant_workflows": [
        "Create Contract: Contracts Tab → New Button → Fill Form → Save",
        "Edit Contract: Select Contract → Edit → Modify Fields → Save",
    ],
    "context_for_video": (
        "You are currently on the Contracts list view in Salesforce Lightning. "
        "To create a new contract, click the blue 'New' button in the top-right corner. "
        "This opens the New Contract form. Fill in the required fields: Account Name "
        "(search and select the account), Contract Start Date, Contract Term in months, "
        "and Status (set to Draft). Optionally add a description and any custom fields. "
        "Once all required fields are filled, click 'Save' at the bottom of the form. "
        "You'll be redirected to the new contract's detail page where you can review "
        "the information and proceed with additional actions like sending for approval."
    ),
    "pages_captured": [
        {
            "url": "https://myorg.lightning.force.com/lightning/o/Contract/list",
            "title": "Recently Viewed | Contracts | Salesforce",
            "screenshot_path": "screenshots/20260520_172555_p8_Recently_Viewed___Contracts___Salesforce.png",
            "dom_summary": {"title": "Contracts", "buttons": ["New", "Import"]},
        },
    ],
}


async def main():
    """Run Agent 2 standalone with sample Agent 1 output."""
    user_query = "How do I create a new contract in Salesforce?"

    print("=" * 60)
    print("FOXIO — Agent 2 Standalone (Video Generation)")
    print(f"Query: {user_query}")
    print(f"Platform: {SAMPLE_AGENT1_OUTPUT['platform_name']}")
    print("=" * 60)

    result = await run_agent2(
        agent1_output=SAMPLE_AGENT1_OUTPUT,
        user_query=user_query,
        dry_run=True,
    )

    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    print(f"Status: {result['status']}")
    print(f"Video Title: {result.get('video_title', 'N/A')}")

    print("\n--- Generated Video Prompts ---")
    for step in result.get("video_prompts", []):
        print(f"\n  Step {step.get('step_number', '?')} ({step.get('duration', 6)}s):")
        print(f"    Prompt: {step.get('prompt', '')[:150]}...")
        print(f"    Narration: {step.get('narration_hint', 'N/A')}")

    if result.get("pipeline_result"):
        pr = result["pipeline_result"]
        print(f"\nPipeline Job ID: {pr.get('job_id')}")
        print(f"Pipeline Status: {pr.get('status')}")


if __name__ == "__main__":
    asyncio.run(main())
