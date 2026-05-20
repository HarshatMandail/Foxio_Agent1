# examples/test_navigate_only.py
"""Test the navigate_and_crawl step independently."""
import asyncio
import logging
import warnings
from pathlib import Path
from dotenv import load_dotenv

from langgraph_browser_agent.nodes import navigate_and_crawl
from langgraph_browser_agent.state import AgentState

load_dotenv()
logging.basicConfig(level=logging.INFO)


async def test_navigate_and_crawl():
    print("🚀 Testing: navigate_and_crawl (multi-page platform capture)\n")

    initial_state: AgentState = {
        "url": "https://www.salesforce.com/",
        "user_query": "How do I create a new contract or opportunity?",
        "page_captures": None,
        "structured_output": None,
    }

    try:
        result_state = await navigate_and_crawl(initial_state)

        captures = result_state.get("page_captures", [])
        print(f"\n{'=' * 70}")
        print(f"✅ Crawl Complete! Pages captured: {len(captures)}\n")

        for i, cap in enumerate(captures, 1):
            screenshot_exists = Path(cap.screenshot_path).exists()
            size_kb = Path(cap.screenshot_path).stat().st_size / 1024 if screenshot_exists else 0
            print(f"  Page {i}:")
            print(f"    Title      : {cap.title}")
            print(f"    URL        : {cap.url[:80]}")
            print(f"    Screenshot : {cap.screenshot_path} ({size_kb:.1f} KB)")
            print(f"    Nav Links  : {len(cap.navigation_links)}")
            print(f"    Buttons    : {len(cap.buttons)}")
            print(f"    Forms      : {cap.forms_count}")
            print()

        print("🎉 Multi-page capture is WORKING!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=ResourceWarning)

    import sys
    if sys.platform == "win32":
        # Suppress "Exception ignored in" pipe errors on Windows shutdown
        import atexit
        atexit.register(lambda: sys.stderr.close())

    asyncio.run(test_navigate_and_crawl())
