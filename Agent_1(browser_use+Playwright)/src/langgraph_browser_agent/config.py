# config.py — Centralized Configuration
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()


# ─── Paths ────────────────────────────────────────────────────────────────────

BASE_DIR = Path(os.getenv("BASE_DIR", "."))
SCREENSHOTS_DIR = Path(os.getenv("SCREENSHOTS_DIR", "screenshots"))
BROWSER_DATA_DIR = Path(os.getenv("BROWSER_DATA_DIR", "browser_data"))
CACHE_DIR = Path(os.getenv("CACHE_DIR", "cache"))
COST_LOG_DIR = Path(os.getenv("COST_LOG_DIR", "logs"))
AUDIT_LOG_DIR = Path(os.getenv("AUDIT_LOG_DIR", "logs/audit"))
AGENT_OUTPUT_DIR = Path(os.getenv("AGENT_OUTPUT_DIR", "logs/agent_output"))
VIDEO_CLIPS_DIR = Path(os.getenv("VIDEO_CLIPS_DIR", "video_clips"))

# Ensure directories exist
for d in [SCREENSHOTS_DIR, BROWSER_DATA_DIR, CACHE_DIR, COST_LOG_DIR, AUDIT_LOG_DIR, AGENT_OUTPUT_DIR, VIDEO_CLIPS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ─── Azure OpenAI ─────────────────────────────────────────────────────────────

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
AZURE_DEPLOYMENT_FULL = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
AZURE_DEPLOYMENT_MINI = os.getenv("AZURE_OPENAI_DEPLOYMENT_MINI", "gpt-4o-mini")

MAX_TOKENS_PER_REQUEST = int(os.getenv("MAX_TOKENS_PER_REQUEST", "8000"))
MAX_COMPLETION_TOKENS = int(os.getenv("MAX_COMPLETION_TOKENS", "2048"))
MAX_COST_PER_SESSION = float(os.getenv("MAX_COST_PER_SESSION_USD", "1.0"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))

ENABLE_CACHE = os.getenv("ENABLE_LLM_CACHE", "true").lower() == "true"
ENABLE_BUDGET_CHECK = os.getenv("ENABLE_BUDGET_CHECK", "true").lower() == "true"
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "21600"))


# ─── Browser ──────────────────────────────────────────────────────────────────

HEADLESS = os.getenv("BROWSER_USE_HEADLESS", "false").lower() == "true"
BROWSER_CHANNEL = os.getenv("BROWSER_CHANNEL", "")
NAVIGATION_TIMEOUT_MS = int(os.getenv("NAVIGATION_TIMEOUT_MS", "30000"))
PAGE_LOAD_TIMEOUT_MS = int(os.getenv("PAGE_LOAD_TIMEOUT_MS", "15000"))
WAIT_FOR_LOGIN_TIMEOUT = int(os.getenv("WAIT_FOR_LOGIN_TIMEOUT", "300"))
LOGIN_CHECK_INTERVAL = int(os.getenv("LOGIN_CHECK_INTERVAL", "3"))


# ─── Security ─────────────────────────────────────────────────────────────────

# URL allowlist — comma-separated domains. Empty = allow all.
_raw_allowlist = os.getenv("URL_ALLOWLIST", "")
URL_ALLOWLIST: list[str] = [
    d.strip().lower() for d in _raw_allowlist.split(",") if d.strip()
]

# Blocked domains — never navigate here regardless of allowlist
_raw_blocklist = os.getenv(
    "URL_BLOCKLIST",
    "localhost,127.0.0.1,0.0.0.0,file://,javascript:,data:,chrome://,about:",
)
URL_BLOCKLIST: list[str] = [
    d.strip().lower() for d in _raw_blocklist.split(",") if d.strip()
]



# ─── Retry / Resilience ──────────────────────────────────────────────────────

MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_BASE_DELAY = float(os.getenv("RETRY_BASE_DELAY", "1.0"))


# ─── Observability ────────────────────────────────────────────────────────────

ENABLE_LANGSMITH = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
LANGSMITH_PROJECT = os.getenv("LANGCHAIN_PROJECT", "foxio-agent1")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


# ─── Validation ───────────────────────────────────────────────────────────────

def validate_url(url: str) -> tuple[bool, str]:
    """Validate a URL against security rules. Returns (is_valid, reason)."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL format"

    if not parsed.scheme or not parsed.netloc:
        return False, "URL must have scheme and domain"

    if parsed.scheme not in ("http", "https"):
        return False, f"Blocked scheme: {parsed.scheme}"

    domain = parsed.netloc.lower().split(":")[0]

    # Check blocklist
    for blocked in URL_BLOCKLIST:
        if blocked in url.lower():
            return False, f"Blocked domain/pattern: {blocked}"

    # Check allowlist (if configured)
    if URL_ALLOWLIST:
        allowed = any(
            domain == allowed_domain or domain.endswith(f".{allowed_domain}")
            for allowed_domain in URL_ALLOWLIST
        )
        if not allowed:
            return False, f"Domain '{domain}' not in allowlist"

    return True, "OK"


def validate_config() -> list[str]:
    """Validate critical configuration. Returns list of errors."""
    errors = []
    if not AZURE_OPENAI_ENDPOINT:
        errors.append("AZURE_OPENAI_ENDPOINT is not set")
    if not AZURE_OPENAI_API_KEY:
        errors.append("AZURE_OPENAI_API_KEY is not set")
    return errors
