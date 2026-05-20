# cost_tracker.py — Azure OpenAI Cost Monitoring & Budget Enforcement
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

COST_LOG_DIR = Path(os.getenv("COST_LOG_DIR", "logs"))
COST_LOG_DIR.mkdir(parents=True, exist_ok=True)

# Azure OpenAI pricing (per 1K tokens) — GPT-4o as of 2024
# Update these if pricing changes
PRICING = {
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
}

# Budget limits from env
MAX_TOKENS_PER_REQUEST = int(os.getenv("MAX_TOKENS_PER_REQUEST", "8000"))
MAX_COST_PER_SESSION = float(os.getenv("MAX_COST_PER_SESSION_USD", "1.0"))


@dataclass
class SessionUsage:
    """Track token usage and cost for a single agent session."""

    session_start: float = field(default_factory=time.time)
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost_usd: float = 0.0
    call_count: int = 0
    cache_hits: int = 0

    def record_call(self, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        """Record a single LLM call's usage."""
        self.call_count += 1
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens

        pricing = PRICING.get(model, PRICING["gpt-4o"])
        cost = (prompt_tokens / 1000 * pricing["input"]) + (
            completion_tokens / 1000 * pricing["output"]
        )
        self.total_cost_usd += cost

        logger.info(
            f"💰 Call #{self.call_count} cost: ${cost:.4f} | "
            f"Session total: ${self.total_cost_usd:.4f}"
        )

    def record_cache_hit(self) -> None:
        """Record a cache hit (saved money)."""
        self.cache_hits += 1

    def is_over_budget(self) -> bool:
        """Check if session has exceeded the cost budget."""
        return self.total_cost_usd >= MAX_COST_PER_SESSION

    def get_summary(self) -> dict:
        """Return session usage summary."""
        return {
            "call_count": self.call_count,
            "cache_hits": self.cache_hits,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "budget_remaining_usd": round(MAX_COST_PER_SESSION - self.total_cost_usd, 4),
            "duration_seconds": round(time.time() - self.session_start, 1),
        }

    def save_log(self) -> None:
        """Persist session usage to a log file."""
        log_file = COST_LOG_DIR / f"session_{int(self.session_start)}.json"
        log_file.write_text(
            json.dumps(self.get_summary(), indent=2), encoding="utf-8"
        )
        logger.info(f"📄 Cost log saved: {log_file}")


# Singleton session tracker
_current_session: Optional[SessionUsage] = None


def get_session() -> SessionUsage:
    """Get or create the current session tracker."""
    global _current_session
    if _current_session is None:
        _current_session = SessionUsage()
    return _current_session


def reset_session() -> None:
    """Reset session tracker (call at start of new agent run)."""
    global _current_session
    if _current_session:
        _current_session.save_log()
    _current_session = SessionUsage()


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English text."""
    return len(text) // 4
