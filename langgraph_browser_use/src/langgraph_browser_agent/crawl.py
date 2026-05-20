# crawl.py — Multi-Page Crawl Logic with Security Filtering
import asyncio
import logging

from playwright.async_api import Page

from .browser_helpers import capture_page
from .config import MAX_PAGES_TO_CRAWL, PAGE_LOAD_TIMEOUT_MS
from .models import PageCapture
from .security import filter_crawl_url

logger = logging.getLogger(__name__)


async def discover_and_crawl(
    page: Page,
    user_query: str,
    audit_log=None,
) -> list[PageCapture]:
    """Crawl multiple pages of the platform to build full context."""
    captures = []
    visited_urls: set[str] = set()

    # Capture the landing page
    capture = await capture_page(page, len(captures) + 1)
    if capture:
        captures.append(capture)
        visited_urls.add(capture.url.split("?")[0].rstrip("/"))
        if audit_log:
            audit_log.log("page_captured", {"url": capture.url, "title": capture.title})

    if not captures:
        return captures

    # Extract navigation links
    nav_links = captures[0].dom_summary.get("navigation", [])
    base_domain = captures[0].url.split("/")[2]

    crawl_queue = [
        link["href"]
        for link in nav_links
        if isinstance(link, dict)
        and filter_crawl_url(link.get("href", ""), base_domain)
        and link.get("href", "").split("?")[0].rstrip("/") not in visited_urls
    ]

    # Salesforce Lightning fallback URLs
    first_url = captures[0].url
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

        # Security check before navigation
        if not filter_crawl_url(link_url, base_domain):
            logger.info(f"Blocked by security filter: {link_url[:80]}")
            if audit_log:
                audit_log.log("url_blocked", {"url": link_url, "reason": "security_filter"})
            continue

        try:
            logger.info(f"Navigating to: {link_url[:80]}")
            if audit_log:
                audit_log.log("navigating", {"url": link_url})

            await page.goto(link_url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
            await asyncio.sleep(3)

            # Check redirect dedup
            actual_url = page.url
            actual_normalized = actual_url.split("?")[0].rstrip("/")
            if actual_normalized in visited_urls and actual_normalized != normalized:
                visited_urls.add(actual_normalized)
                continue
            visited_urls.add(actual_normalized)

            capture = await capture_page(page, len(captures) + 1)
            if capture is None:
                continue
            captures.append(capture)

            if audit_log:
                audit_log.log("page_captured", {"url": capture.url, "title": capture.title})

            # Discover new links from this page
            new_nav = capture.dom_summary.get("navigation", [])
            for nav_item in new_nav:
                if isinstance(nav_item, dict):
                    href = nav_item.get("href", "")
                    href_normalized = href.split("?")[0].rstrip("/")
                    if (
                        filter_crawl_url(href, base_domain)
                        and href_normalized not in visited_urls
                    ):
                        crawl_queue.append(href)

        except Exception as e:
            logger.warning(f"Failed to crawl {link_url[:60]}: {e}")
            if audit_log:
                audit_log.log("crawl_error", {"url": link_url, "error": str(e)})
            continue

    logger.info(f"Total pages captured: {len(captures)}")
    return captures
