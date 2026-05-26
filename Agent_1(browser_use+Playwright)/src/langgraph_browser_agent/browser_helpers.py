# browser_helpers.py — Page Capture, Popup Dismissal, DOM Extraction
import asyncio
import json
import logging
from datetime import datetime

from playwright.async_api import Page

from .config import SCREENSHOTS_DIR
from .models import PageCapture

logger = logging.getLogger(__name__)


async def should_start_recording(page) -> bool:
    """Return True only when we are on the actual Salesforce Home page (skip login page)."""
    url = page.url.lower()
    if "/login" in url or "login.salesforce.com" in url:
        return False
    try:
        await page.wait_for_selector("text='Seller Home' OR text='Home'", timeout=3000)
        return True
    except:
        return False


async def dismiss_common_popups(page):
    """Auto-dismiss common Salesforce popups and modals."""
    selectors = [
        "text=Dismiss", "text=Got it", "text=Close", "text=×",
        "button:has-text('Dismiss')", "button:has-text('Got it')",
        "[data-testid*='dismiss']", ".slds-modal__close", 
        "text=Stay ahead of incidents"
    ]
    for selector in selectors:
        try:
            await page.click(selector, timeout=1500)
            await page.wait_for_timeout(300)
        except:
            pass


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


async def capture_page(page, state):
    if not await should_start_recording(page):
        print("🔇 [capture_page] Skipping login / loading page from recording...")
        return

    # Smart wait - this fixes most slowness
    await page.wait_for_load_state("networkidle", timeout=15000)
    await page.wait_for_timeout(800)

    # Auto-dismiss popups
    await dismiss_common_popups(page)

    # Simple deduplication to avoid duplicate frames
    current_key = f"{page.url}_{len(await page.content())}"
    if getattr(state, "last_ui_key", None) == current_key:
        return
    state.last_ui_key = current_key

    # Existing screenshot + DOM logic continues here...
    # (keep all your original screenshot, context_for_video, etc. code)
