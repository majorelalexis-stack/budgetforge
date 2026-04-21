"""
TDD — RED phase: tests for Slack/Teams block format in AlertService.send_webhook.
These tests must FAIL before the implementation is added.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_slack_url_uses_block_format():
    """Slack Incoming Webhook URLs must receive a payload with 'blocks' and 'text' fields."""
    from services.alert_service import AlertService

    captured = []

    async def mock_post(url, json=None, **kwargs):
        captured.append(json)
        m = MagicMock()
        m.status_code = 200
        return m

    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.post = AsyncMock(side_effect=mock_post)
        MockClient.return_value = mock_instance

        await AlertService.send_webhook(
            url="https://hooks.slack.com/services/T000/B000/xxxx",
            project_name="my-project",
            used_usd=0.85,
            budget_usd=1.0,
        )

    assert len(captured) == 1, "Expected exactly one POST call"
    payload = captured[0]
    assert "blocks" in payload, f"Expected 'blocks' key in Slack payload, got: {list(payload.keys())}"
    assert "text" in payload, f"Expected 'text' key in Slack payload, got: {list(payload.keys())}"


@pytest.mark.asyncio
async def test_generic_url_uses_json_format():
    """Generic webhook URLs must receive the standard JSON payload (no 'blocks')."""
    from services.alert_service import AlertService

    captured = []

    async def mock_post(url, json=None, **kwargs):
        captured.append(json)
        m = MagicMock()
        m.status_code = 200
        return m

    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.post = AsyncMock(side_effect=mock_post)
        MockClient.return_value = mock_instance

        await AlertService.send_webhook(
            url="https://my-server.example.com/webhook",
            project_name="my-project",
            used_usd=0.85,
            budget_usd=1.0,
        )

    assert len(captured) == 1, "Expected exactly one POST call"
    payload = captured[0]
    assert "event" in payload, f"Expected 'event' key in generic payload, got: {list(payload.keys())}"
    assert payload["project"] == "my-project", f"Expected project='my-project', got: {payload.get('project')}"
    assert "blocks" not in payload, f"Generic payload must NOT have 'blocks', got: {list(payload.keys())}"


@pytest.mark.asyncio
async def test_teams_url_uses_block_format():
    """Microsoft Teams (outlook.office.com) webhook URLs must receive a payload with 'text'."""
    from services.alert_service import AlertService

    captured = []

    async def mock_post(url, json=None, **kwargs):
        captured.append(json)
        m = MagicMock()
        m.status_code = 200
        return m

    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.post = AsyncMock(side_effect=mock_post)
        MockClient.return_value = mock_instance

        await AlertService.send_webhook(
            url="https://outlook.office.com/webhook/xxx",
            project_name="my-project",
            used_usd=0.85,
            budget_usd=1.0,
        )

    assert len(captured) == 1, "Expected exactly one POST call"
    payload = captured[0]
    assert "text" in payload, f"Expected 'text' key in Teams payload, got: {list(payload.keys())}"
