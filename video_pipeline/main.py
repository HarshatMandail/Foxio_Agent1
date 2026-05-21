"""
Video Generation Pipeline — Main Entry Point

Supports two modes:
  1. Agent1Output mode: Pass Agent 1 output directly → auto-splits into steps → generates video
  2. Raw steps mode: Pass pre-built steps list → generates video (legacy/testing)

Usage:
    python main.py                    # Run with sample Agent1Output
    python main.py --raw-steps        # Run with raw pre-built steps (legacy)
"""

import asyncio
import sys

from loguru import logger

from config.settings import settings
from generate_tutorial import generate_tutorial_video
from graph.workflow import run_pipeline

# Configure loguru
logger.remove()
logger.add(
    sys.stdout,
    level=settings.log_level,
    format=(
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan> | "
        "<level>{message}</level>"
    ),
)


# Sample Agent1Output (simulating what Agent 1 produces for a CLM platform)
SAMPLE_AGENT1_OUTPUT = {
    "platform_name": "Salesforce",
    "current_page": {
        "url": "https://myorg.lightning.force.com/lightning/o/Contract/list",
        "title": "Recently Viewed | Contracts | Salesforce",
        "description": (
            "The Contracts list view showing all recently viewed contracts "
            "with columns for Contract Number, Account Name, Status, and Start Date."
        ),
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
    "overall_user_journey": (
        "User navigates to Contracts tab → clicks New → "
        "fills contract details → saves the contract."
    ),
    "relevant_workflows": [
        "Create Contract: Contracts Tab → New Button → Fill Form → Save",
        "Edit Contract: Select Contract → Edit → Modify Fields → Save",
        "Send for Approval: Open Contract → Click Submit for Approval → Confirm",
    ],
    "context_for_video": (
        "You are currently on the Contracts list view in Salesforce Lightning. "
        "This page shows all your recently viewed contracts in a table format. "
        "To create a new contract, look at the top-right corner of the page "
        "and click the blue 'New' button. "
        "This opens the New Contract form in a modal window. "
        "First, fill in the Account Name field by clicking on it and searching "
        "for the account you want to associate with this contract. "
        "Next, set the Contract Start Date by clicking the calendar icon "
        "and selecting today's date or your preferred start date. "
        "Then enter the Contract Term in months — for example, type '12' "
        "for a one-year contract. "
        "Set the Status dropdown to 'Draft' since this is a new contract. "
        "Optionally, add a description in the Description field to provide "
        "context about what this contract covers. "
        "Once all required fields are filled, scroll down and click the 'Save' "
        "button at the bottom of the form. "
        "You will be redirected to the new contract's detail page where you can "
        "review all the information and proceed with additional actions like "
        "sending it for approval or attaching documents."
    ),
    "pages_captured": [
        {
            "url": "https://myorg.lightning.force.com/lightning/o/Contract/list",
            "title": "Recently Viewed | Contracts | Salesforce",
            "screenshot_path": "",
            "dom_summary": {"title": "Contracts", "buttons": ["New", "Import"]},
            "navigation_links": [],
            "buttons": [{"text": "New"}],
            "forms_count": 0,
        },
    ],
}


async def run_agent1_to_video() -> None:
    """Run the full Agent1Output → Tutorial Video flow."""
    user_query = "How do I create a new contract in Salesforce?"

    result = await generate_tutorial_video(
        agent1_output=SAMPLE_AGENT1_OUTPUT,
        user_query=user_query,
    )

    _print_result(result)


async def run_raw_steps() -> None:
    """Run with pre-built raw steps (legacy mode for testing)."""
    steps = [
        {
            "prompt": (
                "Screen recording showing a user clicking the 'Create Contract' "
                "button on a CLM dashboard. Clean UI, professional SaaS interface."
            ),
            "duration": 6,
            "aspect_ratio": "16:9",
            "resolution": "480p",
        },
        {
            "prompt": (
                "Screen recording showing a contract template selection modal "
                "appearing with multiple template options. User hovers over "
                "'NDA Template' and selects it."
            ),
            "duration": 8,
            "aspect_ratio": "16:9",
            "resolution": "480p",
        },
        {
            "prompt": (
                "Screen recording showing a contract editor with fields being "
                "auto-filled. The user types a company name in the party field."
            ),
            "duration": 10,
            "aspect_ratio": "16:9",
            "resolution": "480p",
        },
        {
            "prompt": (
                "Screen recording showing the user clicking 'Send for Signature' "
                "button. A success toast notification appears."
            ),
            "duration": 6,
            "aspect_ratio": "16:9",
            "resolution": "480p",
        },
    ]

    logger.info("=" * 60)
    logger.info("VIDEO PIPELINE — Raw Steps Mode")
    logger.info(f"Steps: {len(steps)} | Model: {settings.default_model}")
    logger.info("=" * 60)

    result = await run_pipeline(steps=steps, model_name=settings.default_model)
    _print_result(result)


def _print_result(result: dict) -> None:
    """Print pipeline result summary."""
    logger.info("=" * 60)
    logger.info("RESULT")
    logger.info("=" * 60)
    logger.info(f"Status: {result.get('status')}")
    logger.info(f"Job ID: {result.get('job_id')}")

    if result.get("video_title"):
        logger.info(f"Title: {result['video_title']}")

    if result.get("steps_generated"):
        logger.info(f"Steps: {result['steps_generated']}")

    final_path = result.get("final_video_path", "")
    if final_path and final_path != "dry_run_no_output":
        logger.success(f"Video: {final_path}")
    elif final_path == "dry_run_no_output":
        logger.info("Video: dry_run (no file generated)")

    if result.get("metadata_path"):
        logger.info(f"Metadata: {result['metadata_path']}")

    if result.get("error"):
        logger.error(f"Error: {result['error']}")

    clip_results = result.get("clip_results", [])
    if clip_results:
        success = sum(1 for c in clip_results if c.get("status") in ("success", "dry_run"))
        failed = sum(1 for c in clip_results if c.get("status") == "failed")
        logger.info(f"Clips: {success} success, {failed} failed")


async def main() -> None:
    """Entry point — choose mode based on CLI args."""
    if "--raw-steps" in sys.argv:
        await run_raw_steps()
    else:
        await run_agent1_to_video()


if __name__ == "__main__":
    asyncio.run(main())
