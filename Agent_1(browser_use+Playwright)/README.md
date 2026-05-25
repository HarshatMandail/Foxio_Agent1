# Agent 1 — Foxio CLM/SaaS Page Analyzer

An AI-powered browser agent that analyzes the **user's current screen** on any CLM/SaaS platform and generates step-by-step, beginner-friendly guidance + video-ready context for tutorial generation.

Built for the **Foxio Chrome Extension** — when a user asks "How do I create a contract?" while looking at a specific page, Agent 1 understands exactly what they see and gives precise instructions starting from THAT page.

Built with **LangGraph** for workflow orchestration, **Playwright** for real browser automation, and **Azure OpenAI** for LLM-powered analysis.

## How Agent 1 Works

```
User asks: "How do I create a new contract?"
         ↓
┌─────────────────────────────────────────────────────────────────┐
│  1. CAPTURE CURRENT PAGE                                        │
│     - Screenshot of exactly what the user sees                  │
│     - Full DOM extraction (buttons, forms, navigation, text)    │
│     - Only captures 1-3 pages (focused, not exploratory)        │
├─────────────────────────────────────────────────────────────────┤
│  2. LLM ANALYSIS (GPT-4o-mini for speed + cost)                 │
│     - Understands the exact page the user is on                 │
│     - Generates step-by-step instructions from THIS page        │
│     - Creates video narration script (200-400 words)            │
│     - Uses beginner-friendly language with visual descriptions  │
├─────────────────────────────────────────────────────────────────┤
│  3. OUTPUT → Agent1Output                                       │
│     - current_page: what the user sees right now                │
│     - relevant_workflows: numbered steps to complete the task   │
│     - context_for_video: full narration script for Agent 2      │
└─────────────────────────────────────────────────────────────────┘
```

### Key Behavior: Focused, Not Exploratory

Unlike traditional crawlers, Agent 1 does NOT explore the entire platform. It:
- Captures the **current page** the user is on (always)
- Captures **1-2 related pages** only if the task requires navigation (e.g., clicking "New" opens a form)
- Never crawls unrelated pages (no exploring Contacts when user asked about Contracts)

This makes it **fast** (~20s), **cheap** (~$0.001/query), and **precise**.

## Installation

Requires Python >= 3.10.

```bash
python -m venv .venv
.venv\Scripts\activate  # On Linux/Mac: source .venv/bin/activate
pip install --upgrade pip
pip install -e .
playwright install chromium
```

## Environment Setup

```bash
copy .env.template .env
# Edit .env with your Azure OpenAI credentials
```

Key config for focused behavior:
```env
# How many pages to capture (1 = current only, 2-3 = current + related)
FOCUSED_CRAWL_LIMIT=3
```

## Usage

```python
import asyncio
from langgraph_browser_agent import run_agent1

async def main():
    result = await run_agent1(
        url="https://your-clm-platform.com/contracts",
        user_query="How do I create a new contract?",
    )

    print(f"Platform: {result.platform_name}")
    print(f"Current Page: {result.current_page.title}")

    print("\nSteps:")
    for step in result.relevant_workflows:
        print(f"  {step}")

    print(f"\nVideo Script:\n{result.context_for_video}")

asyncio.run(main())
```

### Example Output

```
Platform: Salesforce
Current Page: Home | Salesforce

Steps:
  Step 1: On the Home page, locate the 'Global Actions' button in the top-right corner ('+' icon). Click on it.
  Step 2: From the dropdown menu, select 'New Contract' or 'New Opportunity'.
  Step 3: Fill in the required fields marked with a red asterisk (*).
  Step 4: Click the 'Save' button at the bottom of the form.
  Step 5: You'll see a success message confirming your record was created.

Video Script:
  You are currently on the Home | Salesforce page. Here's how to create a new contract...
```

## Project Structure

```
src/langgraph_browser_agent/
├── __init__.py          # Public API exports
├── agent.py             # run_agent1() entry point with tracing
├── graph.py             # LangGraph workflow (navigate → analyze → END)
├── nodes.py             # Node functions (focused capture + LLM analysis)
├── models.py            # Pydantic schemas (Agent1Output, PageContext, UIElement)
├── prompts.py           # Foxio-optimized system prompt (video-ready, beginner-friendly)
├── state.py             # AgentState TypedDict
├── config.py            # Centralized configuration with validation
├── security.py          # URL allowlist/blocklist, safe browsing enforcement
├── browser_pool.py      # Browser pooling, reuse, retry logic, graceful cleanup
├── browser_helpers.py   # Page capture, popup dismissal, DOM extraction
├── crawl.py             # Multi-page crawl logic (used in exploratory mode only)
├── llm.py               # Azure OpenAI client with cost controls
├── cache.py             # Response caching layer
├── cost_tracker.py      # Per-call cost tracking with detailed audit
└── logger.py            # Structured logging + audit trail
```

## Production Recommendations

### Security

| Feature | Description | Config |
|---------|-------------|--------|
| URL Allowlist | Only navigate to approved domains | `URL_ALLOWLIST=salesforce.com,hubspot.com` |
| URL Blocklist | Block dangerous patterns (localhost, file://, etc.) | `URL_BLOCKLIST` (defaults provided) |
| Safe Browsing | Only crawl same-domain URLs during discovery | `SAFE_BROWSING_MODE=true` |
| Input Validation | All URLs validated before browser navigation | Automatic |

### Reliability

| Feature | Description | Config |
|---------|-------------|--------|
| Retry with Backoff | Browser operations retry up to 3x with exponential delay | `MAX_RETRIES=3`, `RETRY_BASE_DELAY=1.0` |
| Browser Pool | Reuses browser context across runs (no cold-start) | Automatic |
| Graceful Cleanup | Browser closes cleanly even on crash/timeout | Automatic |
| Timeout Control | Per-navigation and global timeouts | `NAVIGATION_TIMEOUT_MS`, `PAGE_LOAD_TIMEOUT_MS` |

### Performance

| Feature | Description | Impact |
|---------|-------------|--------|
| Focused Capture | Only 1-3 pages instead of 10 | 3x faster, 43x cheaper |
| Browser Pooling | Reuse persistent context | ~3s faster per run |
| LLM Response Cache | Skip duplicate LLM calls | Saves $$ on repeated queries |
| Tiered Models | GPT-4o-mini for focused queries | 97% cheaper than GPT-4o |
| DOM Filtering | Strip noise before LLM | ~40% fewer tokens |

### Observability

| Feature | Description | Config |
|---------|-------------|--------|
| Structured Logging | Timestamped, leveled logs | `LOG_LEVEL=INFO` |
| Audit Trail | JSON log of every action (navigations, captures) | `AUDIT_LOG_DIR=logs/audit` |
| Cost Tracking | Per-call and per-session cost with budget enforcement | `MAX_COST_PER_SESSION_USD=1.0` |
| LangSmith Tracing | Optional LangGraph trace export | `LANGCHAIN_TRACING_V2=true` |

### Deployment Checklist

- [ ] Set `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_API_KEY` in environment (not .env in production)
- [ ] Configure `URL_ALLOWLIST` with approved domains
- [ ] Set `FOCUSED_CRAWL_LIMIT=1` for fastest response (current page only)
- [ ] Set `BROWSER_USE_HEADLESS=true` for server deployment
- [ ] Set `MAX_COST_PER_SESSION_USD` appropriate for your budget
- [ ] Never commit `.env` to version control

## Output Schema

`Agent1Output` contains:

| Field | Description |
|-------|-------------|
| `platform_name` | Detected platform name from branding/title |
| `pages_captured` | List of `PageCapture` with screenshots + DOM |
| `current_page` | What the user sees right now (title, description, key elements, actions) |
| `overall_user_journey` | Where the user is and what they need to do |
| `relevant_workflows` | Numbered step-by-step instructions from the current page |
| `context_for_video` | Full narration script (200-400 words) for Agent 2 video generation |

## Key Dependencies

| Package | Purpose |
|---------|---------|
| `langgraph` | Workflow orchestration |
| `openai` | Azure OpenAI SDK |
| `playwright` | Real browser automation |
| `pydantic` | Output schema validation |
| `python-dotenv` | Environment management |

## License

MIT
