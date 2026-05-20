# Agent 1 — CLM/SaaS Platform Analyzer

An AI-powered browser agent that navigates to any CLM (Contract Lifecycle Management) or SaaS platform URL, extracts interactive DOM elements, and uses GPT-4o to produce a structured analysis of the page — including UI elements, workflows, and video-ready context.

Built with **LangGraph** for workflow orchestration, **browser-use** for headless browser automation, and **LangChain OpenAI** for LLM-powered analysis.

## How It Works

```
┌─────────────┐      ┌─────────────────┐      ┌────────────────────┐
│  Input URL  │ ───► │  Navigate &     │ ───► │  LLM Analysis      │ ───► Structured Output
│  + Query    │      │  Extract DOM    │      │  (GPT-4o)          │
└─────────────┘      └─────────────────┘      └────────────────────┘
```

1. **Navigate** — Opens the target URL in a headless browser, waits for DOM load, and extracts interactive elements (buttons, links, forms, navigation).
2. **Analyze** — Sends the extracted DOM + user query to GPT-4o with a specialized system prompt for UI/UX analysis.
3. **Output** — Returns a structured `Agent1Output` with platform info, page context, workflows, and video-friendly summaries.

## Installation

Requires Python >= 3.10.

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -e .
```

## Environment Setup

Copy `.env.template` to `.env` and set your OpenAI API key:

```bash
cp .env.template .env
```

```env
OPENAI_API_KEY=your_openai_api_key_here
BROWSER_USE_HEADLESS=true
```

## Usage

```python
import asyncio
from langgraph_browser_agent import run_agent1

async def main():
    result = await run_agent1(
        url="https://example-clm-platform.com/contracts",
        user_query="How do I create a new contract?",
    )

    print(f"Platform: {result.platform_name}")
    print(f"Page: {result.current_page.title}")
    print(f"Journey: {result.overall_user_journey}")

    for step in result.relevant_workflows:
        print(f"  - {step}")

    print(f"\nVideo Context:\n{result.context_for_video}")

if __name__ == "__main__":
    asyncio.run(main())
```

See `examples/run_agent1.py` for a complete working example.

## Project Structure

```
src/langgraph_browser_agent/
├── __init__.py      # Public API exports
├── agent.py         # run_agent1() entry point
├── graph.py         # LangGraph workflow definition (navigate → analyze → END)
├── nodes.py         # Node implementations (browser navigation + LLM analysis)
├── models.py        # Pydantic output schemas (Agent1Output, PageContext, UIElement)
├── prompts.py       # System prompt for CLM/SaaS UI analysis
└── state.py         # AgentState TypedDict
```

## Output Schema

`Agent1Output` contains:

| Field | Description |
|-------|-------------|
| `platform_name` | Detected platform name from branding/title |
| `current_page` | `PageContext` with URL, title, description, key UI elements, and main actions |
| `overall_user_journey` | Where the user is and what they can do next |
| `relevant_workflows` | Step-by-step instructions relevant to the query |
| `context_for_video` | Rich summary optimized for generating video tutorials |

## Key Dependencies

| Package | Purpose |
|---------|---------|
| `langgraph` | Workflow orchestration |
| `langchain-openai` | GPT-4o structured output |
| `browser-use` | Headless browser automation |
| `pydantic` | Output schema validation |

## License

MIT
