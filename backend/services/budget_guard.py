from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class BudgetAction(str, Enum):
    BLOCK = "block"
    DOWNGRADE = "downgrade"


class BudgetExceededError(Exception):
    pass


@dataclass
class BudgetStatus:
    allowed: bool
    downgrade_to: Optional[str] = None


_DOWNGRADE_MAP: dict[str, str] = {
    # OpenAI
    "gpt-4o":                   "gpt-4o-mini",
    "gpt-4":                    "gpt-3.5-turbo",
    "gpt-4-turbo":              "gpt-4o-mini",
    "o1":                       "o3-mini",
    # Anthropic
    "claude-opus-4-7":          "claude-haiku-4-5",
    "claude-sonnet-4-6":        "claude-haiku-4-5",
    # Google
    "gemini-1.5-pro":           "gemini-1.5-flash",
    "gemini-2.0-flash-thinking": "gemini-2.0-flash",
    # DeepSeek
    "deepseek-reasoner":        "deepseek-chat",
}


def get_period_start(reset_period: str) -> datetime:
    now = datetime.now()
    if reset_period == "monthly":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if reset_period == "weekly":
        monday = now - timedelta(days=now.weekday())
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)
    return datetime.min


class BudgetGuard:
    def check(
        self,
        budget_usd: float,
        used_usd: float,
        action: BudgetAction,
        current_model: Optional[str] = None,
        downgrade_chain: Optional[list[str]] = None,
    ) -> BudgetStatus:
        if budget_usd <= 0 or used_usd >= budget_usd:
            if action == BudgetAction.DOWNGRADE and current_model:
                # Try project-defined chain first
                if downgrade_chain:
                    for model in downgrade_chain:
                        if model.lower() != current_model.lower():
                            return BudgetStatus(allowed=True, downgrade_to=model)
                # Fall back to built-in map
                fallback = _DOWNGRADE_MAP.get(current_model.lower())
                if fallback:
                    return BudgetStatus(allowed=True, downgrade_to=fallback)
            return BudgetStatus(allowed=False)
        return BudgetStatus(allowed=True)

    def should_alert(self, budget_usd: float, used_usd: float, threshold_pct: int) -> bool:
        if budget_usd <= 0:
            return True
        pct_used = (used_usd / budget_usd) * 100
        return pct_used >= threshold_pct

    def remaining(self, budget_usd: float, used_usd: float) -> float:
        return max(0.0, budget_usd - used_usd)
