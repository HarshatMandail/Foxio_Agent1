# browser_helpers.py — Page Capture, Popup Dismissal, DOM Extraction
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from playwright.async_api import Page

from .config import SCREENSHOTS_DIR
from .models import PageCapture

logger = logging.getLogger(__name__)


def _safe_filename(text: str, max_len: int = 40) -> str:
    return "".join(
        c if c.isalnum() or c in ("_", "-") else "_"
        for c in text[:max_len]
    ).strip("_") or "page"


async def dismiss_popups(page: Page) -> None:
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


async def has_error_page(page: Page) -> bool:
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


_DOM_EXTRACTION_SCRIPT = """() => JSON.stringify({
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
        document.querySelectorAll('nav a, header a, [role="navigation"] a, aside a').forEach(a => {
            addLink(a.textContent, a.href);
        });
        document.querySelectorAll('one-app-nav-bar-item-root').forEach(el => {
            const a = el.querySelector('a') || el.shadowRoot?.querySelector('a');
            const text = el.textContent || el.getAttribute('title') || '';
            const href = a ? a.href : '';
            addLink(text, href);
        });
        document.querySelectorAll(
            'a[href*="/lightning/o/"], a[href*="/lightning/page/"], ' +
            'a[href*="/lightning/r/"], [data-id] a, .slds-nav-vertical__action'
        ).forEach(a => {
            addLink(a.textContent || a.title, a.href);
        });
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
})"""


async def capture_page(page: Page, page_index: int) -> PageCapture | None:
    """Capture screenshot + DOM for the current page. Returns None if error page."""
    try:
        await dismiss_popups(page)
    except Exception:
        pass

    await asyncio.sleep(1)
    try:
        if await has_error_page(page):
            logger.warning("Skipping error/no-access page")
            return None
    except Exception:
        pass

    title = await page.title()
    url = page.url

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = _safe_filename(title)
    screenshot_path = str(SCREENSHOTS_DIR / f"{timestamp}_p{page_index}_{safe_title}.png")

    await page.screenshot(path=screenshot_path, full_page=True)
    logger.info(f"[{page_index}] Screenshot: {screenshot_path}")

    dom_summary = await page.evaluate(_DOM_EXTRACTION_SCRIPT)
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
