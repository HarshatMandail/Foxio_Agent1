# browser_pool.py — Browser Pooling, Retry Logic & Graceful Cleanup
import asyncio
import logging
from typing import Optional

from playwright.async_api import async_playwright, BrowserContext, Page, Playwright

from .config import (
    BROWSER_DATA_DIR,
    BROWSER_CHANNEL,
    HEADLESS,
    MAX_RETRIES,
    RETRY_BASE_DELAY,
    VIDEO_CLIPS_DIR,
)

logger = logging.getLogger(__name__)


class BrowserPool:
    """
    Manages a reusable browser context to avoid cold-start on every run.
    Provides retry logic and graceful cleanup.
    Video recording is enabled by default for all pages.
    """

    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._lock = asyncio.Lock()

    async def acquire(self) -> tuple[BrowserContext, Page]:
        """Get or create a browser context and page."""
        async with self._lock:
            if self._context is None:
                await self._launch()

            try:
                # Verify context is still alive
                pages = self._context.pages
                page = pages[0] if pages else await self._context.new_page()
                # Quick health check
                _ = page.url
                return self._context, page
            except Exception:
                logger.warning("Browser context stale, relaunching...")
                await self._cleanup()
                await self._launch()
                page = self._context.pages[0] if self._context.pages else await self._context.new_page()
                return self._context, page

    async def _launch(self) -> None:
        """Launch a new persistent browser context with video recording enabled."""
        self._playwright = await async_playwright().start()

        launch_kwargs = {
            "user_data_dir": str(BROWSER_DATA_DIR),
            "headless": HEADLESS,
            "viewport": {"width": 1280, "height": 900},
            "record_video_dir": str(VIDEO_CLIPS_DIR),
            "record_video_size": {"width": 1280, "height": 900},
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            "ignore_default_args": ["--enable-automation"],
        }

        if BROWSER_CHANNEL:
            launch_kwargs["channel"] = BROWSER_CHANNEL
            logger.info(f"Using browser channel: {BROWSER_CHANNEL}")

        self._context = await self._playwright.chromium.launch_persistent_context(
            **launch_kwargs
        )

        # Stealth injection
        page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        logger.info("Browser context launched with video recording enabled")

    async def release(self) -> None:
        """Close browser context and playwright (call on shutdown)."""
        async with self._lock:
            await self._cleanup()

    async def _cleanup(self) -> None:
        """Internal cleanup — no lock."""
        if self._context:
            try:
                await self._context.close()
            except Exception as e:
                logger.warning(f"Browser close error (non-fatal): {e}")
            self._context = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None


# Module-level singleton
_pool: Optional[BrowserPool] = None


def get_browser_pool() -> BrowserPool:
    """Get the singleton browser pool instance."""
    global _pool
    if _pool is None:
        _pool = BrowserPool()
    return _pool


async def shutdown_browser_pool() -> None:
    """Gracefully shutdown the browser pool."""
    global _pool
    if _pool:
        await _pool.release()
        _pool = None


# ─── Retry Decorator ──────────────────────────────────────────────────────────

async def retry_async(coro_fn, *args, retries: int = MAX_RETRIES, **kwargs):
    """Execute an async function with exponential backoff retry."""
    last_error = None
    for attempt in range(retries):
        try:
            return await coro_fn(*args, **kwargs)
        except Exception as e:
            last_error = e
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                f"Retry {attempt + 1}/{retries} after error: {e} "
                f"(waiting {delay:.1f}s)"
            )
            await asyncio.sleep(delay)
    raise last_error
