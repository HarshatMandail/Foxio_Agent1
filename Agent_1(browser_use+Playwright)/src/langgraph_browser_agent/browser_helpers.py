# browser_helpers.py — Page Capture, Popup Dismissal, DOM Extraction
import asyncio
import json
import logging
from datetime import datetime

from playwright.async_api import Page

from .config import SCREENSHOTS_DIR
from .models import PageCapture

logger = logging.getLogger(__name__)


def _safe_filename(text: str, max_len: int = 40) -> str:
    return "".join(
        c if c.isalnum() or c in ("_", "-") else "_"
        for c in text[:max_len]
    ).strip("_") or "page"


async def _has_active_form_modal(page: Page) -> bool:
    """Check if there's an active form/record modal open (not a promotional popup)."""
    return await page.evaluate("""() => {
        const dialogs = document.querySelectorAll('[role="dialog"], .slds-modal, .uiModal, .forceModalContainer');
        for (const d of dialogs) {
            const hasForm = d.querySelector('input, select, textarea, form, records-lwc-record-layout, records-record-layout-event-broker');
            if (hasForm) return true;
            const text = (d.textContent || '').toLowerCase();
            if (text.includes('save') || text.includes('required') || text.includes('field')) return true;
        }
        return false;
    }""")


async def dismiss_popups(page: Page, preserve_form_modals: bool = True) -> None:
    """Dismiss common popups/walkthroughs/promotional dialogs.
    If preserve_form_modals=True, will NOT dismiss modals that contain form fields.
    """
    # If there's an active form modal, don't dismiss anything
    if preserve_form_modals:
        try:
            if await _has_active_form_modal(page):
                logger.info("Active form modal detected — skipping popup dismissal")
                return
        except Exception:
            pass

    # Phase 1: JS-based dismissal — only target promotional/walkthrough popups
    await page.evaluate("""() => {
        // Only dismiss popups that are NOT record/form modals
        const isFormModal = (el) => {
            return el.querySelector('input, select, textarea, form, records-lwc-record-layout');
        };

        const dismissTexts = [
            'skip', 'dismiss', 'got it', 'no thanks',
            'not now', 'maybe later', 'remind me later',
        ];
        const allButtons = document.querySelectorAll('button, a[role="button"], [role="button"]');
        allButtons.forEach(btn => {
            const text = (btn.textContent || '').trim().toLowerCase();
            if (dismissTexts.includes(text)) {
                // Make sure this button is NOT inside a form modal
                const parentModal = btn.closest('[role="dialog"], .slds-modal, .uiModal');
                if (!parentModal || !isFormModal(parentModal)) {
                    btn.click();
                }
            }
        });

        const closeSelectors = [
            'button.slds-popover__close',
            '.walkthrough-close', '[data-dismiss]',
            '.slds-notification__close', '.slds-prompt__close',
            'button.toastClose',
        ];
        closeSelectors.forEach(sel => {
            document.querySelectorAll(sel).forEach(el => el.click());
        });
    }""")
    await asyncio.sleep(1)

    # Phase 2: Targeted Playwright dismissal for promotional popups only
    dismiss_selectors = [
        'button:has-text("Dismiss")',
        'button:has-text("Skip")',
        'button:has-text("Not Now")',
        'button:has-text("Got It")',
        '[class*="popover"] button',
        '[class*="walkthrough"] button',
    ]
    for selector in dismiss_selectors:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible(timeout=500):
                # Verify it's not inside a form modal
                is_in_form = await btn.evaluate(
                    """(el) => {
                        const modal = el.closest('[role="dialog"], .slds-modal, .uiModal');
                        if (!modal) return false;
                        return !!modal.querySelector('input, select, textarea, form');
                    }"""
                )
                if not is_in_form:
                    await btn.click()
                    await asyncio.sleep(0.5)
        except Exception:
            continue

    await asyncio.sleep(1)


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
    # Check if a form modal is open (don't dismiss it!)
    has_form_modal = False
    try:
        has_form_modal = await _has_active_form_modal(page)
    except Exception:
        pass

    # Only dismiss popups if there's no active form modal
    if not has_form_modal:
        try:
            await dismiss_popups(page)
        except Exception:
            pass
        await asyncio.sleep(2)
        # Second pass for stubborn popups
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

    # Use viewport screenshot when modal is open (full_page captures background)
    if has_form_modal:
        await page.screenshot(path=screenshot_path, full_page=False)
        logger.info(f"[{page_index}] Screenshot (viewport/modal): {screenshot_path}")
    else:
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
