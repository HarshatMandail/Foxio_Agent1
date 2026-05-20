# examples/run_agent1.py
import asyncio
from agent import run_agent1   # adjust import based on your folder

async def test():
    result = await run_agent1(
        url="https://www.salesforce.com/",   # Test with any CLM/SaaS site
        user_query="How do I create a new opportunity or contract?"
    )
    
    print("Platform:", result.platform_name)
    print("Screenshot:", result.screenshot_path)
    print("Context for Video:", result.context_for_video[:300] + "...")

asyncio.run(test())