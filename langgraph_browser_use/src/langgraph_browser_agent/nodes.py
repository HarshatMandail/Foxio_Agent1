# nodes.py
import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, Page

from .state import AgentState
from .models import Agent1Output, PageCapture, PageContext, UIElement
from .prompts import SYSTEM_PROMPT
from .llm import analyze_with_llm
from .cost_tracker import get_session, reset_session, estimate_tokens

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = Path("screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

BROWSER_DATA_DIR = Path("browser_data")
BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)

MAX_PAGES_TO_CRAWL = 10
WAIT_FOR_LOGIN_TIMEOUT = 300
LOGIN_CHECK_INTERVAL = 3
HEADLESS = os.getenv("BROWSER_USE_HEADLESS", "false").lower() == "true"
BROWSER_CHANNEL = os.getenv("BROWSER_CHANNEL", "")  # Set to "msedge" to use Edge


# ─── URL Detection Helpers ────────────────────────────────────────────────────

def _is_login_page(url: str) -> bool:
    login_indicators = ["/login", "/signin", "/sign-in", "/sso", "/oauth", "/authorize"]
    url_lower = url.lower()
    return any(indicator in url_lower for indicator in login_indicators)


def _is_auth_intermediate_page(url: str) -> bool:
    auth_indicators = [
        "/verification", "/verify", "/mfa", "/two-factor",
        "/challenge", "emailverification", "/_ui/identity/",
    ]
    url_lower = url.lower()
    return any(indicator in url_lower for indicator in auth_indicators)


def _is_post_login_redirect(url: str) -> bool:
    redirect_indicators = ["frontdoor.jsp", "/secur/", "/_ui/identity/"]
    url_lower = url.lower()
    return any(indicator in url_lower for indicator in redirect_indicators)


def _is_app_url(url: str) -> bool:
    url_lower = url.lower()
    app_indicators = ["/lightning/", "/home", "/dashboard", "/app/", "/o/", "/one/one.app"]
    if any(indicator in url_lower for indicator in app_indicators):
        if not _is_login_page(url) and not _is_auth_intermediate_page(url):
            return True
    return False


# ─── Page Helpers ─────────────────────────────────────────────────────────────

def _safe_filename(text: str, max_len: int = 40) -> str:
    return "".join(
        c if c.isalnum() or c in ("_", "-") else "_"
        for c in text[:max_len]
    ).strip("_") or "page"


async def _dismiss_popups(page: Page) -> None:
    """Dismiss common popups/modals/walkthroughs."""
    await page.evaluate("""() => {
        const allButtons = document.querySelectorAll('button, a[role="button"], [role="button"]');
        allButtons.forEach(btn => {
            const text = (btn.textContent || '').trim().toLowerCase();
            if (['skip', 'dismiss', 'got it', 'no thanks', 'close', 'not now'].includes(text)) {
                btn.click();
            }
        });
        const closeSelectors = [
            'button[title="Close"]', 'button[title="Skip"]',
            'button.slds-popover__close', 'button.slds-modal__close',
            '.walkthrough-close', '[data-dismiss]',
        ];
        closeSelectors.forEach(sel => {
            document.querySelectorAll(sel).forEach(el => el.click());
        });
    }""")
    await asyncio.sleep(0.5)
    # Playwright locator fallback for Shadow DOM elements
    try:
        skip_btn = page.locator('button:has-text("Skip")').first
        if await skip_btn.is_visible(timeout=500):
            await skip_btn.click()
    except Exception:
        pass
    try:
        close_btn = page.locator('[class*="popover"] button, [class*="walkthrough"] button').first
        if await close_btn.is_visible(timeout=500):
            await close_btn.click()
    except Exception:
        pass


async def _has_error_page(page: Page) -> bool:
    """Check if the current page shows an access/error message."""
    text = await page.evaluate(
        """() => (document.body.innerText || '').substring(0, 1000).toLowerCase()"""
    )
    error_indicators = [
        "something went wrong",
        "you don't have access",
        "insufficient privileges",
        "no access to this record",
        "ask your administrator",
        "page not found",
    ]
    return any(indicator in text for indicator in error_indicators)


async def _capture_page(page: Page, page_index: int) -> PageCapture | None:
    """Capture screenshot + DOM for the current page. Returns None if error page."""
    try:
        await _dismiss_popups(page)
    except Exception:
        pass

    # Wait briefly for async content, then check for errors
    await asyncio.sleep(1)
    try:
        if await _has_error_page(page):
            logger.warning("⚠️ Skipping error/no-access page")
            return None
    except Exception:
        pass

    title = await page.title()
    url = page.url

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = _safe_filename(title)
    screenshot_path = str(SCREENSHOTS_DIR / f"{timestamp}_p{page_index}_{safe_title}.png")

    await page.screenshot(path=screenshot_path, full_page=True)
    logger.info(f"📸 [{page_index}] Screenshot: {screenshot_path}")

    dom_summary = await page.evaluate("""() => JSON.stringify({
        title: document.title,
        h1: document.querySelector('h1') ? document.querySelector('h1').innerText.trim() : '',
        visible_text: document.body.innerText.substring(0, 2000),
        navigation: (() => {
            const results = [];
            const seen = new Set();
            const addLink = (text, href) => {
                text = (text || '').trim();
                if (text.length > 1 && href && href.startsWith('http') && !seen.has(href)) {
                    seen.add(href);
                    results.push({ text, href });
                }
            };
            // Standard nav links
            document.querySelectorAll('nav a, header a, [role="navigation"] a, aside a').forEach(a => {
                addLink(a.textContent, a.href);
            });
            // Salesforce Lightning nav bar items (pierce into custom elements)
            document.querySelectorAll('one-app-nav-bar-item-root').forEach(el => {
                const a = el.querySelector('a') || el.shadowRoot?.querySelector('a');
                const text = el.textContent || el.getAttribute('title') || '';
                const href = a ? a.href : '';
                addLink(text, href);
            });
            // Fallback: any link pointing to Lightning objects/pages
            document.querySelectorAll(
                'a[href*="/lightning/o/"], a[href*="/lightning/page/"], ' +
                'a[href*="/lightning/r/"], [data-id] a, .slds-nav-vertical__action'
            ).forEach(a => {
                addLink(a.textContent || a.title, a.href);
            });
            // Sidebar/vertical nav in Lightning
            document.querySelectorAll('.appLauncher a, [class*="navItem"] a, [class*="nav-item"] a').forEach(a => {
                addLink(a.textContent || a.title, a.href);
            });
            return results.slice(0, 30);
        })(),
        buttons: Array.from(document.querySelectorAll('button, [role="button"], input[type="submit"]'))
                    .map(b => ({ text: (b.textContent || b.value || '').trim().substring(0, 80), tag: b.tagName.toLowerCase() }))
                    .filter(b => b.text.length > 2)
                    .slice(0, 30),
        forms: Array.from(document.querySelectorAll('form')).length,
        inputs: Array.from(document.querySelectorAll('input, select, textarea'))
                    .map(i => ({ type: i.type || i.tagName.toLowerCase(), name: i.name || '', placeholder: i.placeholder || '' }))
                    .slice(0, 20),
        tables: Array.from(document.querySelectorAll('table')).length,
        modals: Array.from(document.querySelectorAll('[role="dialog"], .modal, .modal-dialog')).length
    })""")

    dom_data = json.loads(dom_summary) if isinstance(dom_summary, str) else dom_summary

    return PageCapture(
        url=url,
        title=title,
        screenshot_path=screenshot_path,
        dom_summary=dom_data,
        navigation_links=[item["text"] for item in dom_data.get("navigation", [])],
        buttons=dom_data.get("buttons", []),
        forms_count=dom_data.get("forms", 0),
    )


# ─── Login Detection ─────────────────────────────────────────────────────────

async def _wait_for_login(page: Page) -> bool:
    """Wait for user to complete full login (including 2FA/verification)."""
    logger.info("⏳ Waiting for login completion... (timeout: 5 minutes)")

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

        # Ignore blank/empty pages
        if current_url in ("about:blank", "", "chrome://newtab/"):
            if elapsed % 30 == 0:
                logger.info(f"   ⏳ Waiting for page to load... ({elapsed}s elapsed)")
            continue

        if current_url != last_url:
            logger.info(f"   🔄 URL changed: {current_url[:80]}")
            last_url = current_url
            stable_app_url_count = 0

        # Primary: URL-based detection — require URL to be stable for 2 checks
        if _is_app_url(current_url):
            stable_app_url_count += 1
            if stable_app_url_count >= 2:
                logger.info(f"✅ Login complete! Dashboard loaded: {current_url[:80]}")
                await asyncio.sleep(3)
                return True
            continue

        if _is_login_page(current_url) or _is_auth_intermediate_page(current_url):
            if elapsed % 30 == 0:
                logger.info(f"   ⏳ Still on auth page... ({elapsed}s elapsed)")
            continue

        if _is_post_login_redirect(current_url):
            continue

        if elapsed % 30 == 0:
            logger.info(f"   ⏳ On unknown page, waiting... ({elapsed}s elapsed)")

    logger.error("❌ Login timeout (5 minutes). Proceeding with current page.")
    return False


# ─── Crawl Logic ──────────────────────────────────────────────────────────────

async def _discover_and_crawl(page: Page, user_query: str) -> list[PageCapture]:
    """Crawl multiple pages of the platform to build full context."""
    captures = []
    visited_urls = set()

    # Capture the landing page
    capture = await _capture_page(page, len(captures) + 1)
    if capture:
        captures.append(capture)
        visited_urls.add(capture.url.split("?")[0].rstrip("/"))

    # Extract navigation links
    nav_links = captures[0].dom_summary.get("navigation", []) if captures else []
    base_domain = captures[0].url.split("/")[2] if captures else ""

    crawl_queue = [
        link["href"] for link in nav_links
        if isinstance(link, dict)
        and link.get("href", "").startswith("http")
        and base_domain in link.get("href", "")
        and "/login" not in link.get("href", "").lower()
        and "/logout" not in link.get("href", "").lower()
        and link.get("href", "").split("?")[0].rstrip("/") not in visited_urls
    ]

    # Salesforce Lightning fallback URLs
    first_url = captures[0].url if captures else ""
    if len(crawl_queue) < 3 and "/lightning/" in first_url:
        base_url = first_url.split("/lightning/")[0] + "/lightning/o/"
        sf_objects = [
            "Contact", "Account", "Opportunity", "Lead",
            "Case", "Contract", "Dashboard",
        ]
        for obj in sf_objects:
            obj_url = f"{base_url}{obj}/list"
            if obj_url.split("?")[0].rstrip("/") not in visited_urls:
                crawl_queue.append(obj_url)

    # Crawl additional pages
    for link_url in crawl_queue:
        if len(captures) >= MAX_PAGES_TO_CRAWL:
            break

        normalized = link_url.split("?")[0].rstrip("/")
        if normalized in visited_urls:
            continue
        visited_urls.add(normalized)

        try:
            logger.info(f"🔗 Navigating to: {link_url}")
            await page.goto(link_url, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(3)

            # Check redirect dedup
            actual_url = page.url
            actual_normalized = actual_url.split("?")[0].rstrip("/")
            if actual_normalized in visited_urls and actual_normalized != normalized:
                visited_urls.add(actual_normalized)
                continue
            visited_urls.add(actual_normalized)

            capture = await _capture_page(page, len(captures) + 1)
            if capture is None:
                continue
            captures.append(capture)

            # Discover new links from this page
            new_nav = capture.dom_summary.get("navigation", [])
            for nav_item in new_nav:
                if isinstance(nav_item, dict):
                    href = nav_item.get("href", "")
                    href_normalized = href.split("?")[0].rstrip("/")
                    if (
                        href.startswith("http")
                        and base_domain in href
                        and href_normalized not in visited_urls
                        and "/login" not in href.lower()
                        and "/logout" not in href.lower()
                    ):
                        crawl_queue.append(href)

        except Exception as e:
            logger.warning(f"⚠️ Failed to crawl {link_url}: {e}")
            continue

    logger.info(f"📋 Total pages captured: {len(captures)}")
    return captures


# ─── Main Node Functions ──────────────────────────────────────────────────────

async def navigate_and_crawl(state: AgentState) -> dict:
    """Navigate to platform, wait for login, then crawl multiple pages."""
    url = state["url"]
    logger.info(f"🚀 Starting platform analysis: {url}")

    # Reset cost tracker for new session
    reset_session()

    async with async_playwright() as pw:
        launch_kwargs = {
            "user_data_dir": str(BROWSER_DATA_DIR),
            "headless": HEADLESS,
            "viewport": {"width": 1280, "height": 900},
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            "ignore_default_args": ["--enable-automation"],
        }

        # Support Edge browser if configured
        if BROWSER_CHANNEL:
            launch_kwargs["channel"] = BROWSER_CHANNEL
            logger.info(f"🌐 Using browser channel: {BROWSER_CHANNEL}")

        browser = await pw.chromium.launch_persistent_context(**launch_kwargs)
        page = browser.pages[0] if browser.pages else await browser.new_page()

        # Stealth: remove navigator.webdriver flag
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        # Navigate to the target URL
        logger.info(f"🌐 Navigating to: {url}")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            logger.info(f"   → Page loaded: {page.url}")
        except Exception as e:
            logger.warning(f"⚠️ Initial navigation issue: {e}")
            logger.info("   → Browser is open. Please navigate manually if needed.")

        # Check if already logged in (e.g., persistent session from browser_data)
        current_url = page.url
        if _is_app_url(current_url):
            logger.info("✅ Already logged in! Skipping login wait.")
        else:
            logger.info("🔐 Login page detected. Please complete login + 2FA in the browser.")
            logger.info("   → Agent will auto-detect when you reach the dashboard.")
            await _wait_for_login(page)

        # Crawl the platform
        captures = await _discover_and_crawl(page, state["user_query"])
        await browser.close()

    return {"page_captures": captures}


# ─── DOM Filtering (Token Optimization) ───────────────────────────────────────

# Noise words in buttons/links that waste tokens
_NOISE_BUTTONS = {
    "skip", "dismiss", "got it", "no thanks", "close", "not now",
    "buy now", "buy starter", "sign up", "see terms", "learn more",
    "save 70%", "upgrade", "try free", "start trial",
}


def _filter_dom_for_llm(dom_summary: dict) -> dict:
    """Strip noise from DOM data before sending to LLM. Saves ~40% tokens."""
    filtered = {}

    # Keep title and h1 (cheap, useful)
    filtered["title"] = dom_summary.get("title", "")
    filtered["h1"] = dom_summary.get("h1", "")

    # Truncate visible_text to 500 chars (was 2000 — mostly noise)
    visible = dom_summary.get("visible_text", "")
    filtered["visible_text"] = visible[:500]

    # Filter navigation — keep only unique, meaningful links
    nav = dom_summary.get("navigation", [])
    seen_texts = set()
    filtered_nav = []
    for item in nav:
        text = item.get("text", "").strip().lower()
        if text and text not in seen_texts and len(text) > 2:
            seen_texts.add(text)
            filtered_nav.append({"text": item["text"], "href": item.get("href", "")})
    filtered["navigation"] = filtered_nav[:15]

    # Filter buttons — remove promotional/noise buttons
    buttons = dom_summary.get("buttons", [])
    filtered["buttons"] = [
        b for b in buttons[:15]
        if b.get("text", "").strip().lower() not in _NOISE_BUTTONS
    ]

    # Keep counts only
    filtered["forms"] = dom_summary.get("forms", 0)
    filtered["tables"] = dom_summary.get("tables", 0)
    filtered["modals"] = dom_summary.get("modals", 0)

    # Skip inputs entirely — rarely useful for workflow understanding
    return filtered


async def analyze_and_generate_output(state: AgentState) -> dict:
    """Analyze captured pages with Azure OpenAI GPT-4o and produce structured Agent1Output."""
    captures = state["page_captures"] or []
    user_query = state["user_query"]

    # Build token-optimized summary (filtered DOM, no raw noise)
    captures_summary = [
        {
            "url": cap.url,
            "title": cap.title,
            "dom": _filter_dom_for_llm(cap.dom_summary),
            "buttons_count": len(cap.buttons),
            "forms_count": cap.forms_count,
        }
        for cap in captures
    ]

    # Compact JSON (no indent) to save tokens
    pages_json = json.dumps(captures_summary, separators=(",", ":"), default=str)

    # Estimate and log input size
    est_tokens = estimate_tokens(pages_json)
    logger.info(f"📏 Input to LLM: ~{est_tokens} tokens ({len(pages_json)} chars) for {len(captures)} pages")

    user_message = f"""Query: {user_query}

Pages ({len(captures)}):
{pages_json}

Respond with JSON:
{{"platform_name":"str","current_page":{{"url":"str","title":"str","description":"str","key_elements":[{{"element_type":"button|link|form|nav","visible_text":"str","purpose":"str","suggested_action":"str"}}],"main_actions":["str"]}},"overall_user_journey":"str","relevant_workflows":["str"],"context_for_video":"str"}}"""

    # Use mini model if < 3 pages (simple analysis), full model for complex
    use_mini = len(captures) <= 2

    try:
        raw = await analyze_with_llm(SYSTEM_PROMPT, user_message, use_mini=use_mini)
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"❌ Failed to parse LLM response: {e}")
        data = {
            "platform_name": "Unknown",
            "current_page": {
                "url": captures[0].url if captures else "",
                "title": captures[0].title if captures else "",
                "description": "Analysis failed — could not parse LLM response.",
                "key_elements": [],
                "main_actions": [],
            },
            "overall_user_journey": "Unable to determine.",
            "relevant_workflows": [],
            "context_for_video": raw[:500] if raw else "",
        }
    except Exception as e:
        logger.error(f"❌ Azure OpenAI call failed: {e}")
        data = {
            "platform_name": "Unknown",
            "current_page": {
                "url": captures[0].url if captures else "",
                "title": captures[0].title if captures else "",
                "description": f"LLM analysis failed: {str(e)}",
                "key_elements": [],
                "main_actions": [],
            },
            "overall_user_journey": "Unable to determine.",
            "relevant_workflows": [],
            "context_for_video": "",
        }

    current_page = PageContext(
        url=data["current_page"]["url"],
        title=data["current_page"]["title"],
        description=data["current_page"]["description"],
        key_elements=[UIElement(**el) for el in data["current_page"].get("key_elements", [])],
        main_actions=data["current_page"].get("main_actions", []),
    )

    # Normalize workflows — LLM may return strings or dicts
    raw_workflows = data.get("relevant_workflows", [])
    workflows = []
    for item in raw_workflows:
        if isinstance(item, str):
            workflows.append(item)
        elif isinstance(item, dict):
            # Extract meaningful text from dict format
            name = item.get("workflow_name", item.get("name", ""))
            steps = item.get("steps", item.get("description", ""))
            if isinstance(steps, list):
                steps = " → ".join(str(s) for s in steps)
            workflows.append(f"{name}: {steps}" if name else str(steps))
        else:
            workflows.append(str(item))

    output = Agent1Output(
        platform_name=data["platform_name"],
        pages_captured=captures,
        current_page=current_page,
        overall_user_journey=data["overall_user_journey"],
        relevant_workflows=workflows,
        context_for_video=data.get("context_for_video", ""),
    )

    # Log session cost summary
    session = get_session()
    summary = session.get_summary()
    logger.info(
        f"💰 Session summary — Calls: {summary['call_count']} | "
        f"Cache hits: {summary['cache_hits']} | "
        f"Cost: ${summary['total_cost_usd']} | "
        f"Budget remaining: ${summary['budget_remaining_usd']}"
    )

    return {"structured_output": output}


# Backward compatibility alias
navigate_to_url = navigate_and_crawl
