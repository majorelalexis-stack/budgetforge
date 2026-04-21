"""TDD RED — BudgetGuard: enforcement des limites de budget."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.budget_guard import BudgetGuard, BudgetAction, BudgetStatus, BudgetExceededError


@pytest.fixture
def guard():
    return BudgetGuard()


class TestBudgetCheck:
    def test_under_budget_returns_allowed(self, guard):
        status = guard.check(budget_usd=100.0, used_usd=50.0, action=BudgetAction.BLOCK)
        assert status.allowed is True
        assert status.downgrade_to is None

    def test_at_exact_budget_returns_blocked_for_block_action(self, guard):
        status = guard.check(budget_usd=100.0, used_usd=100.0, action=BudgetAction.BLOCK)
        assert status.allowed is False

    def test_over_budget_returns_blocked_for_block_action(self, guard):
        status = guard.check(budget_usd=50.0, used_usd=75.0, action=BudgetAction.BLOCK)
        assert status.allowed is False

    def test_over_budget_downgrade_returns_allowed_with_model(self, guard):
        status = guard.check(
            budget_usd=50.0, used_usd=75.0,
            action=BudgetAction.DOWNGRADE,
            current_model="gpt-4o"
        )
        assert status.allowed is True
        assert status.downgrade_to == "gpt-4o-mini"

    def test_over_budget_downgrade_anthropic_opus(self, guard):
        status = guard.check(
            budget_usd=10.0, used_usd=15.0,
            action=BudgetAction.DOWNGRADE,
            current_model="claude-opus-4-7"
        )
        assert status.allowed is True
        assert status.downgrade_to == "claude-haiku-4-5"

    def test_over_budget_downgrade_sonnet_to_haiku(self, guard):
        status = guard.check(
            budget_usd=10.0, used_usd=12.0,
            action=BudgetAction.DOWNGRADE,
            current_model="claude-sonnet-4-6"
        )
        assert status.downgrade_to == "claude-haiku-4-5"

    def test_over_budget_downgrade_unknown_model_blocks(self, guard):
        # Si pas de downgrade connu → bloquer (fail safe)
        status = guard.check(
            budget_usd=10.0, used_usd=15.0,
            action=BudgetAction.DOWNGRADE,
            current_model="some-obscure-model"
        )
        assert status.allowed is False
        assert status.downgrade_to is None

    def test_zero_budget_blocks_immediately(self, guard):
        status = guard.check(budget_usd=0.0, used_usd=0.0, action=BudgetAction.BLOCK)
        assert status.allowed is False

    def test_negative_budget_blocks(self, guard):
        status = guard.check(budget_usd=-5.0, used_usd=0.0, action=BudgetAction.BLOCK)
        assert status.allowed is False


class TestAlertThreshold:
    def test_below_threshold_no_alert(self, guard):
        triggered = guard.should_alert(budget_usd=100.0, used_usd=70.0, threshold_pct=80)
        assert triggered is False

    def test_at_threshold_triggers_alert(self, guard):
        triggered = guard.should_alert(budget_usd=100.0, used_usd=80.0, threshold_pct=80)
        assert triggered is True

    def test_above_threshold_triggers_alert(self, guard):
        triggered = guard.should_alert(budget_usd=100.0, used_usd=95.0, threshold_pct=80)
        assert triggered is True

    def test_threshold_100_triggers_only_at_full_usage(self, guard):
        assert guard.should_alert(budget_usd=100.0, used_usd=99.0, threshold_pct=100) is False
        assert guard.should_alert(budget_usd=100.0, used_usd=100.0, threshold_pct=100) is True

    def test_threshold_zero_always_triggers(self, guard):
        triggered = guard.should_alert(budget_usd=100.0, used_usd=0.01, threshold_pct=0)
        assert triggered is True

    def test_zero_budget_threshold_check(self, guard):
        # Pas de division par zéro
        triggered = guard.should_alert(budget_usd=0.0, used_usd=0.0, threshold_pct=80)
        assert triggered is True  # Budget 0 = toujours alerter


class TestRemainingBudget:
    def test_remaining_budget_computation(self, guard):
        remaining = guard.remaining(budget_usd=100.0, used_usd=37.50)
        assert remaining == pytest.approx(62.50)

    def test_remaining_zero_when_exceeded(self, guard):
        remaining = guard.remaining(budget_usd=100.0, used_usd=150.0)
        assert remaining == 0.0

    def test_remaining_never_negative(self, guard):
        remaining = guard.remaining(budget_usd=10.0, used_usd=999.0)
        assert remaining >= 0.0
