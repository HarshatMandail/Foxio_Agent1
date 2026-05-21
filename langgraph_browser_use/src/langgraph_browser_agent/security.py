# security.py — URL Validation & Safe Browsing
import logging

from .config import validate_url

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Raised when a security check fails."""
    pass


def assert_url_safe(url: str) -> None:
    """Raise SecurityError if URL fails validation."""
    is_valid, reason = validate_url(url)
    if not is_valid:
        raise SecurityError(f"URL blocked: {reason} — {url}")
