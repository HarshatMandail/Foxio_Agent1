# nodes.py — LangGraph Node Functions (Navigate + Analyze)
import asyncio
import json
import logging
import time

from playwright.async_api import Page

from .browser_helpers import capture_page
from .browser_pool import get_browser_pool, retry_async, shutdown_browser_pool
from .config import (
    MAX_PAGES_TO_CRAWL,
    NAVIGATION_TIMEOUT_MS,
    WAIT_FOR_LOGIN_TIMEOUT,
    LOGIN_CHECK_INTERVAL,
)
from .cost_tracker import get_session, reset_session, estimate_tokens
from .crawl import discover_and_crawl
from .llm import analyze_with_llm
from .logger import AuditLogger
from .models import Agent1Output, PageCapture, PageContext, UIElement
from .prompts import SYSTEM_PROMPT
from .security import assert_url_safe, SecurityError
from .state import AgentState

logger = logging.getLogger(__name__)

# How many pages to crawl in focused mode (current page + minimal context)
FOCUSED_CRAWL_LIMIT = int(__import__("os").getenv("FOCUSED_CRAWL_LIMIT", "3"))


# ─── URL Detection Helpers ────────────────────────────────────────────────────

def _is_login_page(url: str) -> bool:
    indicators = ["/login", "/signin", "/sign-in", "/sso", "/oauth", "/authorize"]
    url_lower = url.lower()
    return any(i in url_lower for i in indicators)


def _is_auth_intermediate_page(url: str) -> bool:
    indicators = [
        "/verification", "/verify", "/mfa", "/two-factor",
        "/challenge", "emailverification", "/_ui/identity/",
    ]
    url_lower = url.lower()
    return any(i in url_lower for i in indicators)


def _is_post_login_redirect(url: str) -> bool:
    indicators = ["frontdoor.jsp", "/secur/", "/_ui/identity/"]
    return any(i in url.lower() for i in indicators)


def _is_app_url(url: str) -> bool:
    url_lower = url.lower()
    app_indicators = ["/lightning/", "/home", "/dashboard", "/app/", "/o/", "/one/one.app"]
    if any(i in url_lower for i in app_indicators):
        if not _is_login_page(url) and not _is_auth_intermediate_page(url):
            return True
    return False


# ─── Login Detection ─────────────────────────────────────────────────────────

async def _wait_for_login(page: Page, audit: AuditLogger) -> bool:
    """Wait for user to complete login (including 2FA)."""
    logger.info("Waiting for login completion...")
    audit.log("waiting_for_login")

    elapsed = 0
    last_url = ""
    stable_app_url_count = 0

    while elapsed < WAIT_FOR_LOGIN_TIMEOUT:
        await asyncio.sleep(LOGIN_CHECK_INTERVAL)
        elapsed += LOGIN_CHECK_INTERVAL

        try:
            current_url = page.url
        except Exception:
            continue

        if current_url in ("about:blank", "", "chrome://newtab/"):
            continue

        if current_url != last_url:
            logger.info(f"URL changed: {current_url[:80]}")
            audit.log("url_change", {"url": current_url[:120]})
            last_url = current_url
            stable_app_url_count = 0

        if _is_app_url(current_url):
            stable_app_url_count += 1
            if stable_app_url_count >= 2:
                logger.info(f"Login complete: {current_url[:80]}")
                audit.log("login_complete", {"url": current_url})
                await asyncio.sleep(3)
                return True
            continue

        if _is_login_page(current_url) or _is_auth_intermediate_page(current_url):
            continue

        if _is_post_login_redirect(current_url):
            continue

    logger.error("Login timeout reached. Proceeding with current page.")
    audit.log("login_timeout")
    return False


# ─── DOM Filtering (Token Optimization) ───────────────────────────────────────

_NOISE_BUTTONS = {
    "skip", "dismiss", "got it", "no thanks", "close", "not now",
    "buy now", "buy starter", "sign up", "see terms", "learn more",
    "save 70%", "upgrade", "try free", "start trial",
}


def _filter_dom_for_llm(dom_summary: dict, is_primary_page: bool = False) -> dict:
    """Strip noise from DOM data before sending to LLM.
    Primary page gets more detail; secondary pages get minimal context.
    """
    text_limit = 800 if is_primary_page else 300

    filtered = {
        "title": dom_summary.get("title", ""),
        "h1": dom_summary.get("h1", ""),
        "visible_text": dom_summary.get("visible_text", "")[:text_limit],
    }

    # Navigation — more for primary page
    nav = dom_summary.get("navigation", [])
    seen_texts: set[str] = set()
    filtered_nav = []
    for item in nav:
        text = item.get("text", "").strip().lower()
        if text and text not in seen_texts and len(text) > 2:
            seen_texts.add(text)
            filtered_nav.append({"text": item["text"], "href": item.get("href", "")})
    nav_limit = 20 if is_primary_page else 8
    filtered["navigation"] = filtered_nav[:nav_limit]

    # Buttons — more detail for primary page
    buttons = dom_summary.get("buttons", [])
    btn_limit = 25 if is_primary_page else 10
    filtered["buttons"] = [
        b for b in buttons[:btn_limit]
        if b.get("text", "").strip().lower() not in _NOISE_BUTTONS
    ]

    # Inputs — only for primary page (helps understand forms)
    if is_primary_page:
        filtered["inputs"] = dom_summary.get("inputs", [])[:15]

    filtered["forms"] = dom_summary.get("forms", 0)
    filtered["tables"] = dom_summary.get("tables", 0)
    filtered["modals"] = dom_summary.get("modals", 0)

    return filtered


# ─── Main Node: Navigate & Capture Current Page ──────────────────────────────

async def navigate_and_crawl(state: AgentState) -> dict:
    """Navigate to the user's current page and capture it.
    Focused mode: captures current page + minimal related pages only if needed.
    """
    url = state["url"]
    session_id = str(int(time.time()))
    audit = AuditLogger(session_id)

    logger.info(f"Starting focused page analysis: {url}")
    audit.log("session_start", {"url": url, "query": state["user_query"]})

    # Security: validate URL
    try:
        assert_url_safe(url)
    except SecurityError as e:
        logger.error(f"Security check failed: {e}")
        audit.log("security_blocked", {"url": url, "error": str(e)})
        audit.save()
        return {"page_captures": []}

    # Reset cost tracker
    reset_session()

    pool = get_browser_pool()
    try:
        context, page = await pool.acquire()

        # Navigate to target URL
        async def _navigate():
            await page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)

        try:
            await retry_async(_navigate, retries=2)
            logger.info(f"Page loaded: {page.url}")
            audit.log("page_loaded", {"url": page.url})
        except Exception as e:
            logger.warning(f"Initial navigation issue: {e}")
            audit.log("navigation_error", {"error": str(e)})

        # Check login state
        current_url = page.url
        if _is_app_url(current_url):
            logger.info("Already logged in, skipping login wait.")
            audit.log("already_logged_in")
        else:
            logger.info("Login page detected. Please complete login + 2FA in the browser.")
            await _wait_for_login(page, audit)

        # ─── FOCUSED CAPTURE: Current page is the priority ────────────────
        captures = []

        # 1. Always capture the current page (this is what the user sees)
        primary_capture = await capture_page(page, 1)
        if primary_capture:
            captures.append(primary_capture)
            audit.log("primary_page_captured", {
                "url": primary_capture.url,
                "title": primary_capture.title,
            })

        # 2. Only crawl additional pages if FOCUSED_CRAWL_LIMIT > 1
        #    and the task might require seeing related pages
        if FOCUSED_CRAWL_LIMIT > 1 and captures:
            additional = await _capture_related_pages(
                page, captures[0], state["user_query"], audit,
                max_extra=FOCUSED_CRAWL_LIMIT - 1,
            )
            captures.extend(additional)

    except Exception as e:
        logger.error(f"Browser operation failed: {e}")
        audit.log("browser_error", {"error": str(e)})
        captures = []

    audit.log("capture_complete", {"pages_captured": len(captures)})
    audit.save()

    return {"page_captures": captures}


async def _capture_related_pages(
    page: Page,
    primary: PageCapture,
    user_query: str,
    audit: AuditLogger,
    max_extra: int = 2,
) -> list[PageCapture]:
    """Capture 1-2 related pages only if the user's query implies navigation.
    For example: if user asks 'how to create a contract' and they're on the list view,
    we might capture the 'New Contract' form page too.
    """
    from .config import PAGE_LOAD_TIMEOUT_MS
    from .security import filter_crawl_url

    extra_captures = []
    query_lower = user_query.lower()

    # Keywords that suggest the user needs to navigate to a creation/action page
    action_keywords = ["create", "new", "add", "send", "submit", "approve", "sign", "edit"]
    needs_action_page = any(kw in query_lower for kw in action_keywords)

    if not needs_action_page:
        return extra_captures

    # Look for a relevant "New" or action button/link in the current page DOM
    nav_links = primary.dom_summary.get("navigation", [])
    buttons = primary.dom_summary.get("buttons", [])
    base_domain = primary.url.split("/")[2]

    # Find links that match the user's intent
    target_urls = []
    for link in nav_links:
        if not isinstance(link, dict):
            continue
        href = link.get("href", "")
        text = link.get("text", "").lower()
        if not href or not filter_crawl_url(href, base_domain):
            continue
        # Match link text to query keywords
        if any(kw in text for kw in action_keywords):
            target_urls.append(href)

    # Capture at most max_extra related pages
    visited = {primary.url.split("?")[0].rstrip("/")}
    for target_url in target_urls[:max_extra]:
        normalized = target_url.split("?")[0].rstrip("/")
        if normalized in visited:
            continue
        visited.add(normalized)

        try:
            logger.info(f"Capturing related page: {target_url[:80]}")
            audit.log("navigating_related", {"url": target_url})
            await page.goto(target_url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
            await asyncio.sleep(2)

            cap = await capture_page(page, len(extra_captures) + 2)
            if cap:
                extra_captures.append(cap)
                audit.log("related_page_captured", {"url": cap.url, "title": cap.title})
        except Exception as e:
            logger.warning(f"Failed to capture related page: {e}")
            audit.log("related_page_error", {"url": target_url, "error": str(e)})

    # Navigate back to the original page so user's view is preserved
    if extra_captures:
        try:
            await page.goto(primary.url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
        except Exception:
            pass

    return extra_captures


# ─── Main Node: Analyze & Generate Output ─────────────────────────────────────

async def analyze_and_generate_output(state: AgentState) -> dict:
    """Analyze the current page with LLM and produce task-specific guidance."""
    captures = state["page_captures"] or []
    user_query = state["user_query"]

    if not captures:
        logger.warning("No pages captured — returning empty output")
        return {
            "structured_output": Agent1Output(
                platform_name="Unknown",
                pages_captured=[],
                current_page=PageContext(
                    url="", title="", description="No pages were captured.",
                    key_elements=[], main_actions=[],
                ),
                overall_user_journey="No data available.",
                relevant_workflows=[],
                context_for_video="",
            )
        }

    # Build the LLM input — primary page gets full detail, others get minimal
    primary = captures[0]
    pages_data = []

    for i, cap in enumerate(captures):
        is_primary = (i == 0)
        pages_data.append({
            "page_role": "CURRENT_PAGE (user is looking at this right now)" if is_primary else "RELATED_PAGE",
            "url": cap.url,
            "title": cap.title,
            "dom": _filter_dom_for_llm(cap.dom_summary, is_primary_page=is_primary),
            "buttons_count": len(cap.buttons),
            "forms_count": cap.forms_count,
        })

    pages_json = json.dumps(pages_data, separators=(",", ":"), default=str)

    est_tokens = estimate_tokens(pages_json)
    logger.info(f"Input to LLM: ~{est_tokens} tokens for {len(captures)} pages")

    # Construct a focused user message that emphasizes the current screen
    user_message = (
        f"## User's Question\n"
        f"\"{user_query}\"\n\n"
        f"## Current Screen\n"
        f"The user is currently on: \"{primary.title}\" ({primary.url})\n\n"
        f"## Page Data\n"
        f"{pages_json}\n\n"
        f"## Instructions\n"
        f"Answer the user's question with step-by-step guidance starting from their CURRENT page.\n"
        f"The context_for_video field must be a complete narration script (200-400 words) "
        f"that starts with 'You are currently on the {primary.title} page...' and walks through "
        f"every click and screen transition needed to complete the task.\n"
        f"Respond with JSON matching the schema in your system instructions."
    )

    # Use mini model only for very simple single-page queries
    use_mini = len(captures) == 1 and est_tokens < 2000

    try:
        raw = await analyze_with_llm(SYSTEM_PROMPT, user_message, use_mini=use_mini)
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response: {e}")
        data = _fallback_output(captures, raw if "raw" in dir() else "")
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        data = _fallback_output(captures, str(e))

    # Build structured output
    current_page = PageContext(
        url=data["current_page"]["url"],
        title=data["current_page"]["title"],
        description=data["current_page"]["description"],
        key_elements=[UIElement(**el) for el in data["current_page"].get("key_elements", [])],
        main_actions=data["current_page"].get("main_actions", []),
    )

    workflows = _normalize_workflows(data.get("relevant_workflows", []))

    output = Agent1Output(
        platform_name=data["platform_name"],
        pages_captured=captures,
        current_page=current_page,
        overall_user_journey=data["overall_user_journey"],
        relevant_workflows=workflows,
        context_for_video=data.get("context_for_video", ""),
    )

    # Log cost summary
    session = get_session()
    summary = session.get_summary()
    logger.info(
        f"Session cost: ${summary['total_cost_usd']} | "
        f"Calls: {summary['call_count']} | Cache hits: {summary['cache_hits']}"
    )

    return {"structured_output": output}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _fallback_output(captures: list[PageCapture], error_detail: str) -> dict:
    """Generate fallback output when LLM fails."""
    return {
        "platform_name": "Unknown",
        "current_page": {
            "url": captures[0].url if captures else "",
            "title": captures[0].title if captures else "",
            "description": f"Analysis failed: {error_detail[:200]}",
            "key_elements": [],
            "main_actions": [],
        },
        "overall_user_journey": "Unable to determine.",
        "relevant_workflows": [],
        "context_for_video": "",
    }


def _normalize_workflows(raw_workflows: list) -> list[str]:
    """Normalize workflow items — LLM may return strings or dicts."""
    workflows = []
    for item in raw_workflows:
        if isinstance(item, str):
            workflows.append(item)
        elif isinstance(item, dict):
            name = item.get("workflow_name", item.get("name", ""))
            steps = item.get("steps", item.get("description", ""))
            if isinstance(steps, list):
                steps = " -> ".join(str(s) for s in steps)
            workflows.append(f"{name}: {steps}" if name else str(steps))
        else:
            workflows.append(str(item))
    return workflows


# Backward compatibility alias
navigate_to_url = navigate_and_crawl
