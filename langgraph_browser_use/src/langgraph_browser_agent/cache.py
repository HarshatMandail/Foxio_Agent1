# cache.py — Response Caching Layer
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_DIR = Path(os.getenv("CACHE_DIR", "cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Cache TTL in seconds (default: 6 hours)
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "21600"))


def _generate_cache_key(system_prompt: str, user_message: str) -> str:
    """Generate a deterministic hash key from prompt content."""
    content = f"{system_prompt}|{user_message}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def get_cached_response(system_prompt: str, user_message: str) -> Optional[str]:
    """Return cached LLM response if valid cache exists."""
    key = _generate_cache_key(system_prompt, user_message)
    cache_file = CACHE_DIR / f"{key}.json"

    if not cache_file.exists():
        return None

    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        cached_at = data.get("cached_at", 0)

        if time.time() - cached_at > CACHE_TTL:
            cache_file.unlink()
            logger.info(f"🗑️ Cache expired: {key}")
            return None

        logger.info(f"✅ Cache hit: {key} (saved ~{data.get('tokens_saved', '?')} tokens)")
        return data["response"]
    except (json.JSONDecodeError, KeyError):
        cache_file.unlink(missing_ok=True)
        return None


def save_to_cache(
    system_prompt: str,
    user_message: str,
    response: str,
    tokens_used: int = 0,
) -> None:
    """Save LLM response to cache."""
    key = _generate_cache_key(system_prompt, user_message)
    cache_file = CACHE_DIR / f"{key}.json"

    data = {
        "cached_at": time.time(),
        "response": response,
        "tokens_saved": tokens_used,
    }

    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    logger.info(f"💾 Cached response: {key} ({tokens_used} tokens)")


def clear_cache() -> int:
    """Clear all cached responses. Returns count of files removed."""
    count = 0
    for f in CACHE_DIR.glob("*.json"):
        f.unlink()
        count += 1
    logger.info(f"🧹 Cache cleared: {count} entries removed")
    return count
