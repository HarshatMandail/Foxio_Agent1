# security.py — URL Validation & Safe Browsing
import logging
from urllib.parse import urlparse

from .config import URL_ALLOWLIST, URL_BLOCKLIST, SAFE_BROWSING_MODE, validate_url

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Raised when a security check fails."""
    pass


def assert_url_safe(url: str) -> None:
    """Raise SecurityError if URL fails validation."""
    is_valid, reason = validate_url(url)
    if not is_valid:
        raise SecurityError(f"URL blocked: {reason} — {url}")


def is_same_origin(base_url: str, target_url: str) -> bool:
    """Check if target URL is same-origin as base URL."""
    try:
        base_domain = urlparse(base_url).netloc.lower().split(":")[0]
        target_domain = urlparse(target_url).netloc.lower().split(":")[0]
        return base_domain == target_domain or target_domain.endswith(f".{base_domain}")
    except Exception:
        return False


def filter_crawl_url(url: str, base_domain: str) -> bool:
    """
    Check if a discovered URL is safe to crawl.
    In safe browsing mode, only same-domain URLs are allowed.
    """
    if not url or not url.startswith("http"):
        return False

    # Always block dangerous patterns
    url_lower = url.lower()
    blocked_paths = ["/login", "/logout", "/signout", "/delete", "/admin/destroy"]
    if any(p in url_lower for p in blocked_paths):
        return False

    # Check blocklist
    for blocked in URL_BLOCKLIST:
        if blocked in url_lower:
            return False

    # Safe browsing: restrict to same domain
    if SAFE_BROWSING_MODE:
        try:
            target_domain = urlparse(url).netloc.lower().split(":")[0]
            if base_domain and base_domain not in target_domain:
                return False
        except Exception:
            return False

    # Check allowlist if configured
    if URL_ALLOWLIST:
        try:
            target_domain = urlparse(url).netloc.lower().split(":")[0]
            allowed = any(
                target_domain == d or target_domain.endswith(f".{d}")
                for d in URL_ALLOWLIST
            )
            if not allowed:
                return False
        except Exception:
            return False

    return True
