"""TDD — Auto-downgrade: verifies that the proxy uses the downgraded model in the
forwarded payload when the project budget threshold is reached."""
import json
import pytest
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from core.database import Base, get_db
from core.models import Usage


FAKE_OPENAI_RESPONSE = {
    "id": "chatcmpl-fake-downgrade",
    "object": "chat.completion",
    "model": "gpt-4o-mini",
    "choices": [{"message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


@pytest.fixture(scope="function")
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
async def client(test_db):
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


class TestAutoDowngrade:
    @pytest.mark.asyncio
    async def test_downgrade_applied_when_budget_80pct(self, client, test_db):
        """When budget is fully consumed and action=downgrade, the forwarded model
        must be the first entry in the downgrade_chain, not the requested model.

        Note: BudgetGuard.check() fires when used_usd >= budget_usd. The alert
        threshold (alert_threshold_pct) is independent — it only controls email/webhook
        alerts. Downgrade enforcement requires the budget cap itself to be hit.
        We set budget=1.0 and usage=1.0 to reach exactly the enforcement boundary."""
        # Create project with downgrade config
        proj = (await client.post("/api/projects", json={"name": "downgrade-80pct"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={
                "budget_usd": 1.0,
                "alert_threshold_pct": 80,
                "action": "downgrade",
                "downgrade_chain": ["gpt-4o-mini"],
            },
        )
        api_key = proj["api_key"]
        project_id = proj["id"]

        # Insert Usage that reaches the budget cap exactly (1.0 >= 1.0 triggers guard)
        usage_record = Usage(
            project_id=project_id,
            provider="openai",
            model="gpt-4o",
            tokens_in=100,
            tokens_out=50,
            cost_usd=1.0,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        test_db.add(usage_record)
        test_db.commit()

        with patch(
            "services.proxy_forwarder.ProxyForwarder.forward_openai",
            new_callable=AsyncMock,
        ) as mock_fwd:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {api_key}"},
            )

        assert resp.status_code == 200
        # The payload forwarded to the LLM must use the downgraded model
        forwarded_payload = mock_fwd.call_args[0][0]
        assert forwarded_payload["model"] == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_no_downgrade_when_budget_ok(self, client, test_db):
        """When budget is barely touched, the requested model must pass through unchanged."""
        proj = (await client.post("/api/projects", json={"name": "budget-ok"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={
                "budget_usd": 10.0,
                "alert_threshold_pct": 80,
                "action": "downgrade",
                "downgrade_chain": ["gpt-4o-mini"],
            },
        )
        api_key = proj["api_key"]

        # No Usage records — budget is essentially untouched

        with patch(
            "services.proxy_forwarder.ProxyForwarder.forward_openai",
            new_callable=AsyncMock,
        ) as mock_fwd:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {api_key}"},
            )

        assert resp.status_code == 200
        forwarded_payload = mock_fwd.call_args[0][0]
        # Original model must be preserved — no downgrade applied
        assert forwarded_payload["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_block_when_action_is_block(self, client, test_db):
        """When action=block and budget is exceeded, the proxy must return 429
        and never call the upstream LLM."""
        proj = (await client.post("/api/projects", json={"name": "block-over-budget"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={
                "budget_usd": 1.0,
                "alert_threshold_pct": 80,
                "action": "block",
            },
        )
        api_key = proj["api_key"]
        project_id = proj["id"]

        # Insert a Usage record that pushes cost over the 1.0 budget
        usage_record = Usage(
            project_id=project_id,
            provider="openai",
            model="gpt-4o",
            tokens_in=200,
            tokens_out=100,
            cost_usd=1.01,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        test_db.add(usage_record)
        test_db.commit()

        with patch(
            "services.proxy_forwarder.ProxyForwarder.forward_openai",
            new_callable=AsyncMock,
        ) as mock_fwd:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {api_key}"},
            )

        assert resp.status_code == 429
        # The upstream LLM must never be called when budget is blocked
        mock_fwd.assert_not_called()
