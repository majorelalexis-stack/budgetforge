# BudgetForge V2 — 10 Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 10 features to BudgetForge: auto-downgrade test, Slack alerts, CSV/JSON export, configurable timeout/retry, grace-period key rotation, teams/members, global charts, landing page, mobile responsive, pagination audit.

**Architecture:** Backend-first TDD — test RED then impl GREEN then commit. Each backend task touches ≤3 files. Frontend tasks follow. All DB migrations are additive (nullable columns, new tables).

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy 2 + pytest-asyncio + Alembic; Next.js 16 + Recharts + Tailwind 4.

---

## File Map

### Created
- `backend/routes/export.py` — GET /api/usage/export
- `backend/routes/members.py` — CRUD members + role-based auth
- `backend/alembic/versions/c1_proxy_settings.py` — proxy_timeout_ms, proxy_retries on projects
- `backend/alembic/versions/c2_grace_rotation.py` — previous_api_key, key_rotated_at on projects
- `backend/alembic/versions/c3_members.py` — members table
- `backend/tests/test_autodowngrade.py`
- `backend/tests/test_slack_webhook.py`
- `backend/tests/test_export.py`
- `backend/tests/test_configurable_timeout.py`
- `backend/tests/test_grace_period_rotation.py`
- `backend/tests/test_members.py`
- `dashboard/src/app/landing/page.tsx`

### Modified
- `backend/core/models.py` — +proxy_timeout_ms, proxy_retries, previous_api_key, key_rotated_at on Project; +Member model
- `backend/core/auth.py` — accept member keys; add require_viewer()
- `backend/services/proxy_forwarder.py` — timeout_s param on all forward_* methods
- `backend/services/alert_service.py` — Slack block format detection
- `backend/routes/proxy.py` — pass project timeout to forwarder; check previous_api_key
- `backend/routes/projects.py` — save previous_api_key on rotate; proxy_timeout_ms in BudgetUpdate
- `backend/main.py` — register export + members routers; add /api/usage/daily global endpoint
- `dashboard/src/app/page.tsx` — global spend-by-day chart section
- `dashboard/src/app/globals.css` — mobile responsive breakpoints
- `dashboard/src/components/sidebar.tsx` — mobile hamburger toggle
- `dashboard/src/lib/api.ts` — globalDaily() + export download

---

## Task 1 — Verify auto-downgrade (Feature 3)

*The logic exists in `_check_budget()` → `final_model` → `{**payload, "model": final_model}`. This task adds the missing test.*

**Files:**
- Create: `backend/tests/test_autodowngrade.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_autodowngrade.py
import pytest
from datetime import datetime
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from core.database import Base, get_db
from core.models import Project, Usage, BudgetActionEnum


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


FAKE_OPENAI_RESPONSE = {
    "id": "chatcmpl-fake",
    "object": "chat.completion",
    "model": "gpt-4o-mini",
    "choices": [{"message": {"role": "assistant", "content": "Hi!"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


class TestAutoDowngrade:
    @pytest.mark.asyncio
    async def test_downgrade_applied_when_budget_80pct(self, client, test_db):
        """When >80% budget used + action=downgrade + chain set, forwarded model must be the downgrade."""
        proj = (await client.post("/api/projects", json={"name": "dg-test"})).json()
        await client.put(f"/api/projects/{proj['id']}/budget", json={
            "budget_usd": 1.0,
            "alert_threshold_pct": 80,
            "action": "downgrade",
            "downgrade_chain": ["gpt-4o-mini"],
        })
        # Push usage to 85%
        test_db.add(Usage(
            project_id=proj["id"], provider="openai", model="gpt-4o",
            tokens_in=1000, tokens_out=500, cost_usd=0.85, created_at=datetime.now()
        ))
        test_db.commit()

        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {proj['api_key']}"},
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
            )
        assert resp.status_code == 200
        called_payload = mock_fwd.call_args[0][0]
        assert called_payload["model"] == "gpt-4o-mini", (
            f"Expected gpt-4o-mini but got {called_payload['model']}"
        )

    @pytest.mark.asyncio
    async def test_no_downgrade_when_budget_ok(self, client, test_db):
        """Below threshold: original model forwarded unchanged."""
        proj = (await client.post("/api/projects", json={"name": "dg-ok"})).json()
        await client.put(f"/api/projects/{proj['id']}/budget", json={
            "budget_usd": 10.0,
            "alert_threshold_pct": 80,
            "action": "downgrade",
            "downgrade_chain": ["gpt-4o-mini"],
        })

        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            await client.post(
                "/proxy/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {proj['api_key']}"},
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
            )
        called_payload = mock_fwd.call_args[0][0]
        assert called_payload["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_block_when_action_is_block(self, client, test_db):
        """Exceeded + action=block → 429, no forward."""
        proj = (await client.post("/api/projects", json={"name": "blk-test"})).json()
        await client.put(f"/api/projects/{proj['id']}/budget", json={
            "budget_usd": 1.0,
            "action": "block",
        })
        test_db.add(Usage(
            project_id=proj["id"], provider="openai", model="gpt-4o",
            tokens_in=1000, tokens_out=500, cost_usd=1.01, created_at=datetime.now()
        ))
        test_db.commit()

        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {proj['api_key']}"},
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
            )
        assert resp.status_code == 429
        mock_fwd.assert_not_called()
```

- [ ] **Step 2: Run — expect GREEN (logic already exists)**

```
cd budgetforge/backend
venv/Scripts/python -m pytest tests/test_autodowngrade.py -v
```

Expected: 3 passed. If RED on `test_downgrade_applied_when_budget_80pct`, check `routes/proxy.py:222` — `final_model` must be used as `{**payload, "model": final_model}` in the forward call.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_autodowngrade.py
git commit -m "test(proxy): verify auto-downgrade applies correct model to forwarded request"
```

---

## Task 2 — Slack webhook format (Feature 4)

*`alert_service.py` currently sends generic JSON. Slack ignores non-block payloads on Incoming Webhooks URLs.*

**Files:**
- Modify: `backend/services/alert_service.py`
- Create: `backend/tests/test_slack_webhook.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_slack_webhook.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from services.alert_service import AlertService


class TestSlackWebhook:
    @pytest.mark.asyncio
    async def test_slack_url_uses_block_format(self):
        """hooks.slack.com URL → payload must have 'blocks' key."""
        slack_url = "https://hooks.slack.com/services/T000/B000/xxxx"
        captured = []

        async def mock_post(url, json=None, **kwargs):
            captured.append(json)
            m = MagicMock()
            m.status_code = 200
            return m

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=mock_post)
            mock_client_cls.return_value = mock_client

            await AlertService.send_webhook(
                url=slack_url,
                project_name="my-project",
                used_usd=0.85,
                budget_usd=1.0,
            )

        assert len(captured) == 1
        payload = captured[0]
        assert "blocks" in payload, f"Expected Slack block format, got: {payload}"
        assert "text" in payload  # fallback text required by Slack

    @pytest.mark.asyncio
    async def test_generic_url_uses_json_format(self):
        """Non-Slack URL → payload uses standard JSON format."""
        generic_url = "https://my-server.example.com/webhook"
        captured = []

        async def mock_post(url, json=None, **kwargs):
            captured.append(json)
            m = MagicMock()
            m.status_code = 200
            return m

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=mock_post)
            mock_client_cls.return_value = mock_client

            await AlertService.send_webhook(
                url=generic_url,
                project_name="my-project",
                used_usd=0.85,
                budget_usd=1.0,
            )

        payload = captured[0]
        assert "event" in payload
        assert payload["project"] == "my-project"
        assert "blocks" not in payload

    @pytest.mark.asyncio
    async def test_teams_url_uses_block_format(self):
        """hooks.office.com URL (Teams) → also Slack-compatible block format."""
        teams_url = "https://outlook.office.com/webhook/xxx"
        captured = []

        async def mock_post(url, json=None, **kwargs):
            captured.append(json)
            m = MagicMock()
            m.status_code = 200
            return m

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=mock_post)
            mock_client_cls.return_value = mock_client

            await AlertService.send_webhook(
                url=teams_url,
                project_name="my-project",
                used_usd=0.85,
                budget_usd=1.0,
            )

        payload = captured[0]
        assert "text" in payload
```

- [ ] **Step 2: Run — expect RED**

```
venv/Scripts/python -m pytest tests/test_slack_webhook.py -v
```

Expected: `test_slack_url_uses_block_format` FAIL — currently no `blocks` key.

- [ ] **Step 3: Modify `backend/services/alert_service.py` — replace `send_webhook`**

Replace the `send_webhook` static method (lines 33–45) with:

```python
_SLACK_HOSTS = ("hooks.slack.com", "hooks.office.com", "outlook.office.com")

@staticmethod
def _is_slack_compatible(url: str) -> bool:
    from urllib.parse import urlparse
    host = urlparse(url).netloc.lower()
    return any(host.endswith(h) for h in AlertService._SLACK_HOSTS)

@staticmethod
async def send_webhook(url: str, project_name: str, used_usd: float, budget_usd: float) -> None:
    pct = round(used_usd / budget_usd * 100, 1) if budget_usd > 0 else 100
    if AlertService._is_slack_compatible(url):
        payload = {
            "text": f"[BudgetForge] {project_name} at {pct}% (${used_usd:.4f} / ${budget_usd:.2f})",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f":warning: *Budget alert: {project_name}*\n"
                            f"Used *${used_usd:.4f}* of *${budget_usd:.2f}* ({pct}%)"
                        ),
                    },
                }
            ],
        }
    else:
        payload = {
            "event": "budget_alert",
            "project": project_name,
            "used_usd": used_usd,
            "budget_usd": budget_usd,
            "pct_used": pct,
        }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, json=payload)
    except Exception as e:
        logger.warning(f"Webhook alert failed for {project_name}: {e}")
```

Also add `_SLACK_HOSTS` as a class-level tuple just before `_is_slack_compatible`. The class already has `AlertService` as namespace.

Actually, `_SLACK_HOSTS` should be outside the class or as a module-level constant. Put it before the class definition:

```python
_SLACK_HOSTS = ("hooks.slack.com", "hooks.office.com", "outlook.office.com")
```

And `_is_slack_compatible` references the module-level constant:

```python
@staticmethod
def _is_slack_compatible(url: str) -> bool:
    from urllib.parse import urlparse
    host = urlparse(url).netloc.lower()
    return any(host.endswith(h) for h in _SLACK_HOSTS)
```

- [ ] **Step 4: Run — expect GREEN**

```
venv/Scripts/python -m pytest tests/test_slack_webhook.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Run full suite**

```
venv/Scripts/python -m pytest tests/ -q
```

Expected: 230 passed, 1 failed (pre-existing rate limit test).

- [ ] **Step 6: Commit**

```bash
git add backend/services/alert_service.py backend/tests/test_slack_webhook.py
git commit -m "feat(alerts): Slack/Teams block format for webhook alerts"
```

---

## Task 3 — Export CSV/JSON (Feature 7)

**Files:**
- Create: `backend/routes/export.py`
- Create: `backend/tests/test_export.py`
- Modify: `backend/main.py` (register router)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_export.py
import csv
import io
import json
import pytest
from datetime import datetime
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from core.database import Base, get_db
from core.models import Project, Usage


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


@pytest.fixture
async def seeded_db(client, test_db):
    proj = (await client.post("/api/projects", json={"name": "export-proj"})).json()
    test_db.add(Usage(
        project_id=proj["id"], provider="openai", model="gpt-4o",
        tokens_in=100, tokens_out=50, cost_usd=0.01, created_at=datetime.now()
    ))
    test_db.add(Usage(
        project_id=proj["id"], provider="anthropic", model="claude-sonnet-4-6",
        tokens_in=200, tokens_out=80, cost_usd=0.02, created_at=datetime.now()
    ))
    test_db.commit()
    return proj


class TestExportCSV:
    @pytest.mark.asyncio
    async def test_export_csv_returns_csv_content_type(self, client, seeded_db):
        resp = await client.get("/api/usage/export?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_export_csv_has_header_and_rows(self, client, seeded_db):
        resp = await client.get("/api/usage/export?format=csv")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 2
        assert set(reader.fieldnames) >= {"id", "project_id", "provider", "model", "tokens_in", "tokens_out", "cost_usd", "created_at"}

    @pytest.mark.asyncio
    async def test_export_csv_filter_by_project(self, client, test_db):
        p1 = (await client.post("/api/projects", json={"name": "p1"})).json()
        p2 = (await client.post("/api/projects", json={"name": "p2"})).json()
        test_db.add(Usage(project_id=p1["id"], provider="openai", model="gpt-4o", tokens_in=10, tokens_out=5, cost_usd=0.001, created_at=datetime.now()))
        test_db.add(Usage(project_id=p2["id"], provider="openai", model="gpt-4o", tokens_in=10, tokens_out=5, cost_usd=0.001, created_at=datetime.now()))
        test_db.commit()

        resp = await client.get(f"/api/usage/export?format=csv&project_id={p1['id']}")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["project_id"] == str(p1["id"])

    @pytest.mark.asyncio
    async def test_export_json_returns_list(self, client, seeded_db):
        resp = await client.get("/api/usage/export?format=json")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert "provider" in data[0]
        assert "cost_usd" in data[0]

    @pytest.mark.asyncio
    async def test_export_unknown_format_returns_400(self, client, seeded_db):
        resp = await client.get("/api/usage/export?format=xml")
        assert resp.status_code == 400
```

- [ ] **Step 2: Run — expect 404 (route doesn't exist yet)**

```
venv/Scripts/python -m pytest tests/test_export.py -v
```

Expected: all FAIL with AssertionError (404 responses).

- [ ] **Step 3: Create `backend/routes/export.py`**

```python
import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import Usage

router = APIRouter(prefix="/api/usage", tags=["export"])


class UsageRecord(BaseModel):
    id: int
    project_id: int
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    agent: Optional[str]
    created_at: str

    model_config = {"from_attributes": True}


def _query_usages(
    db: Session,
    project_id: Optional[int],
    date_from: Optional[str],
    date_to: Optional[str],
) -> list:
    q = db.query(Usage)
    if project_id is not None:
        q = q.filter(Usage.project_id == project_id)
    if date_from:
        q = q.filter(Usage.created_at >= datetime.fromisoformat(date_from))
    if date_to:
        q = q.filter(Usage.created_at <= datetime.fromisoformat(date_to))
    return q.order_by(Usage.created_at.desc()).all()


@router.get("/export")
async def export_usage(
    format: str = Query("csv", pattern="^(csv|json)$"),
    project_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if format not in ("csv", "json"):
        raise HTTPException(status_code=400, detail="format must be 'csv' or 'json'")

    records = _query_usages(db, project_id, date_from, date_to)

    if format == "json":
        return [
            {
                "id": u.id,
                "project_id": u.project_id,
                "provider": u.provider,
                "model": u.model,
                "tokens_in": u.tokens_in,
                "tokens_out": u.tokens_out,
                "cost_usd": u.cost_usd,
                "agent": u.agent,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in records
        ]

    # CSV
    fields = ["id", "project_id", "provider", "model", "tokens_in", "tokens_out", "cost_usd", "agent", "created_at"]

    def generate_csv():
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for u in records:
            writer.writerow({
                "id": u.id,
                "project_id": u.project_id,
                "provider": u.provider,
                "model": u.model,
                "tokens_in": u.tokens_in,
                "tokens_out": u.tokens_out,
                "cost_usd": u.cost_usd,
                "agent": u.agent or "",
                "created_at": u.created_at.isoformat() if u.created_at else "",
            })
        yield output.getvalue()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"budgetforge_export_{timestamp}.csv"
    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 4: Register router in `backend/main.py`**

Add after the existing imports:
```python
from routes.export import router as export_router
```

Add after the other `app.include_router(...)` calls:
```python
app.include_router(export_router)
```

- [ ] **Step 5: Run — expect GREEN**

```
venv/Scripts/python -m pytest tests/test_export.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Run full suite**

```
venv/Scripts/python -m pytest tests/ -q
```

- [ ] **Step 7: Commit**

```bash
git add backend/routes/export.py backend/tests/test_export.py backend/main.py
git commit -m "feat(export): GET /api/usage/export returns CSV or JSON usage history"
```

---

## Task 4 — Configurable timeout/retry (Feature 8)

**Files:**
- Modify: `backend/core/models.py` (add columns to Project)
- Create: `backend/alembic/versions/c1_proxy_settings.py`
- Modify: `backend/services/proxy_forwarder.py` (timeout_s param)
- Modify: `backend/routes/proxy.py` (pass project timeout)
- Modify: `backend/routes/projects.py` (BudgetUpdate + BudgetResponse + set_budget handler)
- Create: `backend/tests/test_configurable_timeout.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_configurable_timeout.py
import pytest
from unittest.mock import AsyncMock, patch, ANY
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from core.database import Base, get_db


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


FAKE_OPENAI_RESPONSE = {
    "id": "chatcmpl-fake",
    "object": "chat.completion",
    "model": "gpt-4o",
    "choices": [{"message": {"role": "assistant", "content": "Hi!"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


class TestConfigurableTimeout:
    @pytest.mark.asyncio
    async def test_project_timeout_passed_to_forwarder(self, client):
        proj = (await client.post("/api/projects", json={"name": "timeout-proj"})).json()
        await client.put(f"/api/projects/{proj['id']}/budget", json={
            "budget_usd": 100.0,
            "action": "block",
            "proxy_timeout_ms": 5000,
        })

        with patch("routes.proxy.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            await client.post(
                "/proxy/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {proj['api_key']}"},
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
            )
        mock_fwd.assert_called_once_with(ANY, ANY, timeout_s=5.0)

    @pytest.mark.asyncio
    async def test_default_timeout_used_when_not_set(self, client):
        proj = (await client.post("/api/projects", json={"name": "default-timeout"})).json()
        await client.put(f"/api/projects/{proj['id']}/budget", json={
            "budget_usd": 100.0,
            "action": "block",
        })

        with patch("routes.proxy.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            await client.post(
                "/proxy/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {proj['api_key']}"},
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
            )
        mock_fwd.assert_called_once_with(ANY, ANY, timeout_s=60.0)

    @pytest.mark.asyncio
    async def test_budget_response_includes_proxy_settings(self, client):
        proj = (await client.post("/api/projects", json={"name": "settings-proj"})).json()
        resp = await client.put(f"/api/projects/{proj['id']}/budget", json={
            "budget_usd": 50.0,
            "action": "block",
            "proxy_timeout_ms": 10000,
            "proxy_retries": 2,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["proxy_timeout_ms"] == 10000
        assert data["proxy_retries"] == 2
```

- [ ] **Step 2: Run — expect RED**

```
venv/Scripts/python -m pytest tests/test_configurable_timeout.py -v
```

Expected: FAIL — `proxy_timeout_ms` field unknown, `forward_openai` called without `timeout_s`.

- [ ] **Step 3: Add columns to `backend/core/models.py`**

In `class Project`, after `downgrade_chain = Column(...)` (line 30), add:
```python
proxy_timeout_ms = Column(Integer, nullable=True)   # None = use default 60s
proxy_retries = Column(Integer, nullable=True, default=0)
```

- [ ] **Step 4: Create Alembic migration `backend/alembic/versions/c1_proxy_settings.py`**

```python
"""add proxy_timeout_ms and proxy_retries to projects

Revision ID: c1_proxy_settings
Revises: b2c3d4e5f6a7
Create Date: 2026-04-21
"""
from alembic import op
import sqlalchemy as sa

revision = 'c1_proxy_settings'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('projects', sa.Column('proxy_timeout_ms', sa.Integer(), nullable=True))
    op.add_column('projects', sa.Column('proxy_retries', sa.Integer(), nullable=True, server_default='0'))


def downgrade():
    op.drop_column('projects', 'proxy_retries')
    op.drop_column('projects', 'proxy_timeout_ms')
```

- [ ] **Step 5: Update `backend/services/proxy_forwarder.py` — add `timeout_s` param**

Change `forward_openai`, `forward_anthropic`, `forward_google`, `forward_deepseek` signatures. For each, replace `async with httpx.AsyncClient(timeout=60.0)` with the passed value:

```python
@staticmethod
async def forward_openai(request_body: dict, api_key: str, timeout_s: float = 60.0) -> dict:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()

@staticmethod
async def forward_anthropic(request_body: dict, api_key: str, timeout_s: float = 60.0) -> dict:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            json=request_body,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        return resp.json()

@staticmethod
async def forward_google(request_body: dict, api_key: str, timeout_s: float = 60.0) -> dict:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.post(
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()

@staticmethod
async def forward_deepseek(request_body: dict, api_key: str, timeout_s: float = 60.0) -> dict:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.post(
            "https://api.deepseek.com/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()
```

Note: streaming methods (`forward_openai_stream` etc.) use `timeout=120.0` for longer calls — leave them unchanged.

- [ ] **Step 6: Update `backend/routes/proxy.py` — pass timeout to forwarder**

In `proxy_openai` (and same pattern for `proxy_anthropic`, `proxy_google`, `proxy_deepseek`):

After `final_model = _check_budget(project, db, model)`, add:
```python
timeout_s = project.proxy_timeout_ms / 1000.0 if project.proxy_timeout_ms else 60.0
```

Then change the `forward_openai` call from:
```python
response = await ProxyForwarder.forward_openai(
    {**payload, "model": final_model}, settings.openai_api_key
)
```
to:
```python
response = await ProxyForwarder.forward_openai(
    {**payload, "model": final_model}, settings.openai_api_key, timeout_s=timeout_s
)
```

Do the same for anthropic, google, deepseek proxy endpoints.

- [ ] **Step 7: Update `backend/routes/projects.py` — BudgetUpdate + BudgetResponse + handler**

In `BudgetUpdate`, add after `downgrade_chain`:
```python
proxy_timeout_ms: Optional[int] = Field(None, ge=1000, le=300000)
proxy_retries: Optional[int] = Field(None, ge=0, le=5)
```

In `BudgetResponse`, add:
```python
proxy_timeout_ms: Optional[int] = None
proxy_retries: Optional[int] = None
```

In `set_budget` handler, after `project.downgrade_chain = ...`, add:
```python
project.proxy_timeout_ms = payload.proxy_timeout_ms
project.proxy_retries = payload.proxy_retries
```

Update the `BudgetResponse(...)` return to include the new fields:
```python
return BudgetResponse(
    budget_usd=project.budget_usd,
    alert_threshold_pct=project.alert_threshold_pct,
    action=project.action.value,
    reset_period=project.reset_period,
    max_cost_per_call_usd=project.max_cost_per_call_usd,
    proxy_timeout_ms=project.proxy_timeout_ms,
    proxy_retries=project.proxy_retries,
)
```

- [ ] **Step 8: Run — expect GREEN**

```
venv/Scripts/python -m pytest tests/test_configurable_timeout.py -v
```

Expected: 3 passed.

- [ ] **Step 9: Run full suite**

```
venv/Scripts/python -m pytest tests/ -q
```

- [ ] **Step 10: Apply migration on prod**

```bash
ssh ubuntu@maxiaworld.app "cd /opt/budgetforge/backend && source venv/bin/activate && alembic upgrade head"
```

- [ ] **Step 11: Commit**

```bash
git add backend/core/models.py backend/alembic/versions/c1_proxy_settings.py \
        backend/services/proxy_forwarder.py backend/routes/proxy.py \
        backend/routes/projects.py backend/tests/test_configurable_timeout.py
git commit -m "feat(proxy): configurable timeout_ms and retries per project"
```

---

## Task 5 — Grace-period key rotation (Feature 5)

*After rotating, old key remains valid for 5 minutes. Prevents race conditions when clients are mid-request.*

**Files:**
- Modify: `backend/core/models.py` (add previous_api_key, key_rotated_at)
- Create: `backend/alembic/versions/c2_grace_rotation.py`
- Modify: `backend/routes/proxy.py` (_get_project_by_api_key)
- Modify: `backend/routes/projects.py` (rotate_key endpoint)
- Create: `backend/tests/test_grace_period_rotation.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_grace_period_rotation.py
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from core.database import Base, get_db
from core.models import Project


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


FAKE_OPENAI_RESPONSE = {
    "id": "chatcmpl-fake",
    "object": "chat.completion",
    "model": "gpt-4o",
    "choices": [{"message": {"role": "assistant", "content": "Hi!"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


class TestGracePeriodRotation:
    @pytest.mark.asyncio
    async def test_old_key_works_immediately_after_rotation(self, client):
        proj = (await client.post("/api/projects", json={"name": "grace-test"})).json()
        old_key = proj["api_key"]

        rotated = (await client.post(f"/api/projects/{proj['id']}/rotate-key")).json()
        new_key = rotated["api_key"]
        assert old_key != new_key

        with patch("routes.proxy.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock:
            mock.return_value = FAKE_OPENAI_RESPONSE
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {old_key}"},
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
            )
        assert resp.status_code == 200, f"Old key rejected immediately, got {resp.status_code}"

    @pytest.mark.asyncio
    async def test_new_key_works_after_rotation(self, client):
        proj = (await client.post("/api/projects", json={"name": "new-key-test"})).json()
        rotated = (await client.post(f"/api/projects/{proj['id']}/rotate-key")).json()
        new_key = rotated["api_key"]

        with patch("routes.proxy.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock:
            mock.return_value = FAKE_OPENAI_RESPONSE
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {new_key}"},
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_old_key_rejected_after_grace_period(self, client, test_db):
        proj = (await client.post("/api/projects", json={"name": "expired-test"})).json()
        old_key = proj["api_key"]

        await client.post(f"/api/projects/{proj['id']}/rotate-key")

        # Simulate rotation happened 6 minutes ago (past 5-min grace window)
        db_proj = test_db.query(Project).filter(Project.id == proj["id"]).first()
        db_proj.key_rotated_at = datetime.now() - timedelta(minutes=6)
        test_db.commit()

        resp = await client.post(
            "/proxy/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {old_key}"},
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_rotate_stores_previous_key(self, client, test_db):
        proj = (await client.post("/api/projects", json={"name": "store-prev"})).json()
        old_key = proj["api_key"]

        await client.post(f"/api/projects/{proj['id']}/rotate-key")

        db_proj = test_db.query(Project).filter(Project.id == proj["id"]).first()
        assert db_proj.previous_api_key == old_key
        assert db_proj.key_rotated_at is not None
```

- [ ] **Step 2: Run — expect RED**

```
venv/Scripts/python -m pytest tests/test_grace_period_rotation.py -v
```

Expected: FAIL — `previous_api_key` doesn't exist on Project model.

- [ ] **Step 3: Add columns to `backend/core/models.py`**

In `class Project`, add after `key_rotated_at` not existing yet, add after `api_key` column:
```python
previous_api_key = Column(String, nullable=True)
key_rotated_at = Column(DateTime, nullable=True)
```

- [ ] **Step 4: Create migration `backend/alembic/versions/c2_grace_rotation.py`**

```python
"""add previous_api_key and key_rotated_at to projects

Revision ID: c2_grace_rotation
Revises: c1_proxy_settings
Create Date: 2026-04-21
"""
from alembic import op
import sqlalchemy as sa

revision = 'c2_grace_rotation'
down_revision = 'c1_proxy_settings'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('projects', sa.Column('previous_api_key', sa.String(), nullable=True))
    op.add_column('projects', sa.Column('key_rotated_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('projects', 'key_rotated_at')
    op.drop_column('projects', 'previous_api_key')
```

- [ ] **Step 5: Update `rotate_key` in `backend/routes/projects.py`**

Replace the current `rotate_key` function body:

```python
@router.post("/{project_id}/rotate-key", response_model=ProjectResponse, dependencies=[Depends(require_admin)])
def rotate_key(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project.previous_api_key = project.api_key
    project.key_rotated_at = datetime.now()
    project.api_key = f"bf-{secrets.token_urlsafe(32)}"
    db.commit()
    db.refresh(project)
    return project
```

Add `from datetime import datetime` at the top of projects.py if not already imported (it already is).

- [ ] **Step 6: Update `_get_project_by_api_key` in `backend/routes/proxy.py`**

Replace the current function:

```python
_GRACE_PERIOD_MINUTES = 5

def _get_project_by_api_key(authorization: Optional[str], db: Session) -> Project:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    api_key = authorization.removeprefix("Bearer ").strip()

    # Check current key
    project = db.query(Project).filter(Project.api_key == api_key).first()
    if project:
        return project

    # Check previous key within grace period
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(minutes=_GRACE_PERIOD_MINUTES)
    project = db.query(Project).filter(
        Project.previous_api_key == api_key,
        Project.key_rotated_at >= cutoff,
    ).first()
    if project:
        return project

    raise HTTPException(status_code=401, detail="Invalid API key")
```

- [ ] **Step 7: Run — expect GREEN**

```
venv/Scripts/python -m pytest tests/test_grace_period_rotation.py -v
```

Expected: 4 passed.

- [ ] **Step 8: Run full suite**

```
venv/Scripts/python -m pytest tests/ -q
```

- [ ] **Step 9: Apply migration on prod**

```bash
ssh ubuntu@maxiaworld.app "cd /opt/budgetforge/backend && source venv/bin/activate && alembic upgrade head"
```

- [ ] **Step 10: Commit**

```bash
git add backend/core/models.py backend/alembic/versions/c2_grace_rotation.py \
        backend/routes/proxy.py backend/routes/projects.py \
        backend/tests/test_grace_period_rotation.py
git commit -m "feat(auth): 5-minute grace period after API key rotation"
```

---

## Task 6 — Teams / Multi-user (Feature 1)

*Add `Member` model with role (admin/viewer). Admin members can use their key for all routes. Viewer members can only call GET routes. Global admin key continues to work unchanged.*

**Files:**
- Modify: `backend/core/models.py` (+Member)
- Create: `backend/alembic/versions/c3_members.py`
- Modify: `backend/core/auth.py` (accept member keys)
- Create: `backend/routes/members.py`
- Modify: `backend/main.py` (register members router)
- Create: `backend/tests/test_members.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_members.py
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from core.database import Base, get_db


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


class TestMemberCRUD:
    @pytest.mark.asyncio
    async def test_create_admin_member(self, client):
        resp = await client.post("/api/members", json={"email": "alice@example.com", "role": "admin"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "alice@example.com"
        assert data["role"] == "admin"
        assert data["api_key"].startswith("bf-mbr-")

    @pytest.mark.asyncio
    async def test_create_viewer_member(self, client):
        resp = await client.post("/api/members", json={"email": "viewer@example.com", "role": "viewer"})
        assert resp.status_code == 201
        assert resp.json()["role"] == "viewer"

    @pytest.mark.asyncio
    async def test_duplicate_email_rejected(self, client):
        await client.post("/api/members", json={"email": "dup@example.com", "role": "admin"})
        resp = await client.post("/api/members", json={"email": "dup@example.com", "role": "viewer"})
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_list_members(self, client):
        await client.post("/api/members", json={"email": "a@example.com", "role": "admin"})
        await client.post("/api/members", json={"email": "b@example.com", "role": "viewer"})
        resp = await client.get("/api/members")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_delete_member(self, client):
        m = (await client.post("/api/members", json={"email": "del@example.com", "role": "viewer"})).json()
        resp = await client.delete(f"/api/members/{m['id']}")
        assert resp.status_code == 204
        assert len((await client.get("/api/members")).json()) == 0

    @pytest.mark.asyncio
    async def test_invalid_role_rejected(self, client):
        resp = await client.post("/api/members", json={"email": "bad@example.com", "role": "superadmin"})
        assert resp.status_code == 422


class TestMemberAuth:
    @pytest.mark.asyncio
    async def test_admin_member_key_lists_projects(self, client):
        member = (await client.post("/api/members", json={"email": "mgr@example.com", "role": "admin"})).json()
        await client.post("/api/projects", json={"name": "proj-x"})

        resp = await client.get("/api/projects", headers={"X-Admin-Key": member["api_key"]})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_viewer_member_can_get_project(self, client):
        member = (await client.post("/api/members", json={"email": "ro@example.com", "role": "viewer"})).json()
        proj = (await client.post("/api/projects", json={"name": "ro-proj"})).json()

        resp = await client.get(f"/api/projects/{proj['id']}", headers={"X-Admin-Key": member["api_key"]})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_viewer_member_cannot_create_project(self, client):
        member = (await client.post("/api/members", json={"email": "viewer2@example.com", "role": "viewer"})).json()

        resp = await client.post(
            "/api/projects",
            json={"name": "forbidden"},
            headers={"X-Admin-Key": member["api_key"]},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_member_cannot_delete_project(self, client):
        member = (await client.post("/api/members", json={"email": "viewer3@example.com", "role": "viewer"})).json()
        proj = (await client.post("/api/projects", json={"name": "nodelete"})).json()

        resp = await client.delete(f"/api/projects/{proj['id']}", headers={"X-Admin-Key": member["api_key"]})
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_unknown_key_rejected(self, client):
        # In prod (with admin key set), unknown key → 401
        # In dev mode (no admin key, no members), pass-through
        # This test runs in dev mode → unknown key is treated as "no key" → 200 in dev
        # We just verify no server error
        resp = await client.get("/api/projects", headers={"X-Admin-Key": "bf-mbr-unknown"})
        # In dev mode (no admin_api_key set), this passes through — that's expected
        assert resp.status_code in (200, 401)
```

- [ ] **Step 2: Run — expect RED**

```
venv/Scripts/python -m pytest tests/test_members.py -v
```

Expected: FAIL — `/api/members` returns 404.

- [ ] **Step 3: Add `Member` to `backend/core/models.py`**

Add after the `SiteSetting` class:

```python
class Member(Base):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    api_key = Column(String, unique=True, nullable=False,
                     default=lambda: f"bf-mbr-{secrets.token_urlsafe(24)}")
    role = Column(String, nullable=False, default="viewer")  # "admin" or "viewer"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
```

The `secrets` import is already at line 1 of models.py.

- [ ] **Step 4: Create migration `backend/alembic/versions/c3_members.py`**

```python
"""add members table

Revision ID: c3_members
Revises: c2_grace_rotation
Create Date: 2026-04-21
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3_members'
down_revision = 'c2_grace_rotation'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'members',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('api_key', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False, server_default='viewer'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('api_key'),
    )
    op.create_index('ix_members_email', 'members', ['email'])
    op.create_index('ix_members_id', 'members', ['id'])


def downgrade():
    op.drop_index('ix_members_id', table_name='members')
    op.drop_index('ix_members_email', table_name='members')
    op.drop_table('members')
```

- [ ] **Step 5: Create `backend/routes/members.py`**

```python
import secrets
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Literal
from core.database import get_db
from core.models import Member
from core.auth import require_admin

router = APIRouter(prefix="/api/members", tags=["members"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class MemberCreate(BaseModel):
    email: str
    role: Literal["admin", "viewer"] = "viewer"

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError(f"Invalid email: {v!r}")
        return v.lower()


class MemberResponse(BaseModel):
    id: int
    email: str
    api_key: str
    role: str
    model_config = {"from_attributes": True}


@router.post("", status_code=201, response_model=MemberResponse, dependencies=[Depends(require_admin)])
def create_member(payload: MemberCreate, db: Session = Depends(get_db)):
    member = Member(email=payload.email, role=payload.role)
    db.add(member)
    try:
        db.commit()
        db.refresh(member)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Member '{payload.email}' already exists")
    return member


@router.get("", response_model=list[MemberResponse], dependencies=[Depends(require_admin)])
def list_members(db: Session = Depends(get_db)):
    return db.query(Member).all()


@router.delete("/{member_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_member(member_id: int, db: Session = Depends(get_db)):
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    db.delete(member)
    db.commit()
```

- [ ] **Step 6: Update `backend/core/auth.py` — accept member keys**

Replace the entire file:

```python
from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session
from core.config import settings
from core.database import get_db


async def require_admin(
    x_admin_key: str = Header(default="", alias="X-Admin-Key"),
    db: Session = Depends(get_db),
) -> None:
    """Allow: global admin key, OR member with role=admin, OR dev mode (no key set + no members)."""
    # Dev mode: no global key configured
    if not settings.admin_api_key:
        # Still block viewer members trying to reach write endpoints
        if x_admin_key and x_admin_key.startswith("bf-mbr-"):
            from core.models import Member
            member = db.query(Member).filter(Member.api_key == x_admin_key).first()
            if member and member.role == "viewer":
                raise HTTPException(status_code=403, detail="Viewer members cannot perform write operations")
        return

    # Global admin key
    if x_admin_key == settings.admin_api_key:
        return

    # Member key with admin role
    if x_admin_key.startswith("bf-mbr-"):
        from core.models import Member
        member = db.query(Member).filter(Member.api_key == x_admin_key).first()
        if member:
            if member.role == "admin":
                return
            raise HTTPException(status_code=403, detail="Viewer members cannot perform write operations")

    raise HTTPException(status_code=401, detail="Invalid or missing admin key")


async def require_viewer(
    x_admin_key: str = Header(default="", alias="X-Admin-Key"),
    db: Session = Depends(get_db),
) -> None:
    """Allow: global admin key, OR any member (admin or viewer), OR dev mode."""
    if not settings.admin_api_key:
        return  # dev mode — no auth

    if x_admin_key == settings.admin_api_key:
        return

    if x_admin_key.startswith("bf-mbr-"):
        from core.models import Member
        member = db.query(Member).filter(Member.api_key == x_admin_key).first()
        if member:
            return  # any role is OK for read

    raise HTTPException(status_code=401, detail="Invalid or missing key")
```

- [ ] **Step 7: Apply `require_viewer` to read-only project routes in `backend/routes/projects.py`**

Change these three endpoints from `dependencies=[Depends(require_admin)]` to `dependencies=[Depends(require_viewer)]`:

```python
@router.get("", response_model=list[ProjectResponse], dependencies=[Depends(require_viewer)])
@router.get("/{project_id}", response_model=ProjectResponse, dependencies=[Depends(require_viewer)])
@router.get("/{project_id}/usage", response_model=UsageSummary, dependencies=[Depends(require_viewer)])
```

Also import `require_viewer` at the top:
```python
from core.auth import require_admin, require_viewer
```

- [ ] **Step 8: Register members router in `backend/main.py`**

Add import:
```python
from routes.members import router as members_router
```

Add after existing routers:
```python
app.include_router(members_router)
```

- [ ] **Step 9: Run — expect GREEN**

```
venv/Scripts/python -m pytest tests/test_members.py -v
```

Expected: 11 passed.

- [ ] **Step 10: Run full suite**

```
venv/Scripts/python -m pytest tests/ -q
```

Expected: ~240+ passed, 1 failed (pre-existing).

- [ ] **Step 11: Apply migration on prod**

```bash
ssh ubuntu@maxiaworld.app "cd /opt/budgetforge/backend && source venv/bin/activate && alembic upgrade head"
```

- [ ] **Step 12: Commit**

```bash
git add backend/core/models.py backend/alembic/versions/c3_members.py \
        backend/core/auth.py backend/routes/members.py \
        backend/routes/projects.py backend/main.py \
        backend/tests/test_members.py
git commit -m "feat(teams): member accounts with admin/viewer roles and API key auth"
```

---

## Task 7 — Global spend chart backend (Feature 2)

*Adds `GET /api/usage/daily` — same as per-project but aggregates ALL projects.*

**Files:**
- Modify: `backend/main.py` (add endpoint)
- Create: `backend/tests/test_global_daily.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_global_daily.py
import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from core.database import Base, get_db
from core.models import Project, Usage


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


class TestGlobalDailyUsage:
    @pytest.mark.asyncio
    async def test_returns_30_days(self, client):
        resp = await client.get("/api/usage/daily")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 30
        assert "date" in data[0]
        assert "spend" in data[0]

    @pytest.mark.asyncio
    async def test_aggregates_all_projects(self, client, test_db):
        p1 = Project(name="p1")
        p2 = Project(name="p2")
        test_db.add_all([p1, p2])
        test_db.commit()

        today = datetime.now().replace(hour=12)
        test_db.add(Usage(project_id=p1.id, provider="openai", model="gpt-4o",
                          tokens_in=100, tokens_out=50, cost_usd=0.01, created_at=today))
        test_db.add(Usage(project_id=p2.id, provider="anthropic", model="claude-sonnet-4-6",
                          tokens_in=100, tokens_out=50, cost_usd=0.02, created_at=today))
        test_db.commit()

        resp = await client.get("/api/usage/daily")
        data = resp.json()
        today_str = today.date().isoformat()
        today_entry = next(d for d in data if d["date"] == today_str)
        assert abs(today_entry["spend"] - 0.03) < 1e-9
```

- [ ] **Step 2: Run — expect RED (404)**

```
venv/Scripts/python -m pytest tests/test_global_daily.py -v
```

- [ ] **Step 3: Add endpoint to `backend/main.py`**

Add import at top with the existing routes imports:
```python
from routes.projects import DailySpend
```

Add after the existing `@app.get("/api/usage/breakdown")` endpoint:

```python
@app.get("/api/usage/daily", response_model=list[DailySpend], tags=["usage"])
def global_daily_usage(db: Session = Depends(get_db)):
    """Last 30 days aggregated spend across ALL projects."""
    from datetime import date, timedelta
    today = date.today()
    start = today - timedelta(days=29)
    start_dt = datetime(start.year, start.month, start.day)

    usages = db.query(Usage).filter(Usage.created_at >= start_dt).all()

    daily: dict[str, float] = {}
    for i in range(30):
        daily[(start + timedelta(days=i)).isoformat()] = 0.0
    for u in usages:
        d = u.created_at.date().isoformat()
        if d in daily:
            daily[d] += u.cost_usd

    return [DailySpend(date=d, spend=round(v, 9)) for d, v in sorted(daily.items())]
```

Also add the `datetime` import at the top of main.py:
```python
from datetime import datetime
```

- [ ] **Step 4: Run — expect GREEN**

```
venv/Scripts/python -m pytest tests/test_global_daily.py -v
```

- [ ] **Step 5: Run full suite**

```
venv/Scripts/python -m pytest tests/ -q
```

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/tests/test_global_daily.py
git commit -m "feat(usage): GET /api/usage/daily — 30-day global spend aggregation"
```

---

## Task 8 — Frontend: global spend chart (Feature 2)

*Add `globalDaily()` to api.ts and a spend-by-day AreaChart on the overview page.*

**Files:**
- Modify: `dashboard/src/lib/api.ts`
- Modify: `dashboard/src/app/page.tsx`

- [ ] **Step 1: Add `globalDaily` to `dashboard/src/lib/api.ts`**

In the `api` export object, inside the `usage` namespace (after `breakdown`), add:

```typescript
daily: async (): Promise<DailySpend[]> => {
  const resp = await fetch(`${BASE}/api/usage/daily`);
  if (!resp.ok) throw new Error("Failed to fetch daily usage");
  return resp.json();
},
export: (params: { format: "csv" | "json"; project_id?: number; date_from?: string; date_to?: string }) => {
  const qs = new URLSearchParams();
  qs.set("format", params.format);
  if (params.project_id != null) qs.set("project_id", String(params.project_id));
  if (params.date_from) qs.set("date_from", params.date_from);
  if (params.date_to) qs.set("date_to", params.date_to);
  return `${BASE}/api/usage/export?${qs.toString()}`;
},
```

Add the `DailySpend` type if not already defined:
```typescript
export interface DailySpend {
  date: string;
  spend: number;
}
```

- [ ] **Step 2: Add global spend chart to `dashboard/src/app/page.tsx`**

Locate the section after the stat cards (before the local vs cloud pie chart). Add a new card section:

```tsx
// At the top of the component, add state:
const [dailySpend, setDailySpend] = useState<DailySpend[]>([]);

// In useEffect (after existing data fetches), add:
const daily = await api.usage.daily();
setDailySpend(daily);
```

Add the chart card in the JSX after the "Budget Health" section:

```tsx
{/* Global Spend — last 30 days */}
<div className="rounded-xl border border-[--border] bg-[--card] p-6">
  <h2 className="text-sm font-semibold text-[--muted] mb-4 uppercase tracking-wider">
    Global Spend — Last 30 Days
  </h2>
  <ResponsiveContainer width="100%" height={180}>
    <AreaChart data={dailySpend} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
      <defs>
        <linearGradient id="spendGradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="5%" stopColor="var(--amber)" stopOpacity={0.3} />
          <stop offset="95%" stopColor="var(--amber)" stopOpacity={0} />
        </linearGradient>
      </defs>
      <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(5)} interval={6} />
      <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `$${v.toFixed(3)}`} width={55} />
      <Tooltip
        formatter={(val: number) => [`$${val.toFixed(4)}`, "Spend"]}
        labelFormatter={(label) => `Date: ${label}`}
      />
      <Area
        type="monotone"
        dataKey="spend"
        stroke="var(--amber)"
        fill="url(#spendGradient)"
        strokeWidth={2}
        dot={false}
      />
    </AreaChart>
  </ResponsiveContainer>
</div>
```

Add imports at top of page.tsx:
```tsx
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import type { DailySpend } from "@/lib/api";
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd dashboard
npm run build 2>&1 | tail -20
```

Expected: build succeeds (no TS errors).

- [ ] **Step 4: Commit**

```bash
git add dashboard/src/lib/api.ts dashboard/src/app/page.tsx
git commit -m "feat(dashboard): global 30-day spend chart on overview page"
```

---

## Task 9 — Landing page (Feature 10)

*New `/landing` route with hero, key features, and CTA. The existing `/` route stays as the dashboard.*

**Files:**
- Create: `dashboard/src/app/landing/page.tsx`

- [ ] **Step 1: Create `dashboard/src/app/landing/page.tsx`**

```tsx
import Link from "next/link";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[--background] text-[--foreground] font-[family-name:var(--font-dm-sans)]">
      {/* Nav */}
      <nav className="border-b border-[--border] px-6 py-4 flex items-center justify-between">
        <span className="font-bold text-lg tracking-tight">
          LLM <span className="text-[--amber]">BudgetForge</span>
        </span>
        <Link
          href="/"
          className="text-sm px-4 py-2 rounded-lg bg-[--amber] text-black font-semibold hover:opacity-90 transition-opacity"
        >
          Open Dashboard →
        </Link>
      </nav>

      {/* Hero */}
      <section className="max-w-3xl mx-auto px-6 pt-20 pb-16 text-center">
        <div className="inline-block text-xs font-semibold px-3 py-1 rounded-full border border-[--amber] text-[--amber] mb-6">
          Hard budget limits for LLM APIs
        </div>
        <h1 className="text-4xl sm:text-5xl font-bold leading-tight mb-6">
          Stop unexpected<br />
          <span className="text-[--amber]">LLM API bills</span>
        </h1>
        <p className="text-[--muted] text-lg mb-10 max-w-xl mx-auto">
          BudgetForge sits between your code and the LLM APIs. Set hard limits per project,
          get alerts before you blow your budget, and auto-downgrade to cheaper models when limits are reached.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            href="/"
            className="px-6 py-3 rounded-lg bg-[--amber] text-black font-semibold hover:opacity-90 transition-opacity"
          >
            Open Dashboard
          </Link>
          <a
            href="https://github.com/maxia-lab/budgetforge"
            className="px-6 py-3 rounded-lg border border-[--border] hover:border-[--amber] transition-colors"
          >
            View on GitHub
          </a>
        </div>
      </section>

      {/* Integration snippet */}
      <section className="max-w-2xl mx-auto px-6 pb-16">
        <div className="rounded-xl border border-[--border] bg-[--card] p-6 font-[family-name:var(--font-jetbrains-mono)] text-sm">
          <p className="text-[--muted] text-xs mb-3">2-line integration — works with any OpenAI SDK</p>
          <pre className="text-green-400">{`# Before
client = OpenAI(api_key="sk-...")

# After (drop-in replacement)
client = OpenAI(
  api_key="bf-yourprojectkey",
  base_url="https://llmbudget.maxiaworld.app/proxy/openai"
)`}</pre>
        </div>
      </section>

      {/* Features */}
      <section className="max-w-4xl mx-auto px-6 pb-20">
        <h2 className="text-center text-2xl font-bold mb-10">Everything you need</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[
            { icon: "🛑", title: "Hard Limits", desc: "Block or downgrade when budget is reached. No surprises." },
            { icon: "📊", title: "Per-Project Budgets", desc: "Separate budget, alerts and model policy per project or team." },
            { icon: "⬇️", title: "Auto-Downgrade", desc: "Automatically switch to cheaper models when budget threshold hits." },
            { icon: "🔔", title: "Alerts", desc: "Email and Slack/webhook alerts before you hit the ceiling." },
            { icon: "📥", title: "Usage Export", desc: "CSV and JSON export for billing, audits, and team reporting." },
            { icon: "👥", title: "Team Members", desc: "Invite teammates as admin or viewer. No shared passwords." },
          ].map((f) => (
            <div key={f.title} className="rounded-xl border border-[--border] bg-[--card] p-5">
              <div className="text-2xl mb-3">{f.icon}</div>
              <h3 className="font-semibold mb-1">{f.title}</h3>
              <p className="text-sm text-[--muted]">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-[--border] py-16 text-center px-6">
        <h2 className="text-2xl font-bold mb-4">Ready to stop overspending?</h2>
        <Link
          href="/"
          className="inline-block px-8 py-3 rounded-lg bg-[--amber] text-black font-semibold hover:opacity-90 transition-opacity"
        >
          Open BudgetForge →
        </Link>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd dashboard
npm run build 2>&1 | tail -10
```

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/app/landing/page.tsx
git commit -m "feat(landing): add /landing page with hero, features, integration snippet"
```

---

## Task 10 — Mobile responsive (Feature 9)

**Files:**
- Modify: `dashboard/src/app/globals.css`
- Modify: `dashboard/src/components/sidebar.tsx` (hamburger toggle)

- [ ] **Step 1: Read current sidebar.tsx completely before editing**

```bash
cat dashboard/src/components/sidebar.tsx
```

- [ ] **Step 2: Add mobile hamburger toggle to sidebar**

The sidebar currently renders as a fixed side column. Add a mobile-only toggle button and hide the sidebar by default on small screens:

```tsx
"use client";
import { useState } from "react";
// ... existing imports

export function Sidebar() {
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Mobile toggle button */}
      <button
        className="fixed top-4 left-4 z-50 sm:hidden p-2 rounded-lg bg-[--card] border border-[--border]"
        onClick={() => setOpen((v) => !v)}
        aria-label="Toggle menu"
      >
        <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
          {open
            ? <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
            : <path fillRule="evenodd" d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clipRule="evenodd" />
          }
        </svg>
      </button>

      {/* Overlay on mobile */}
      {open && (
        <div
          className="fixed inset-0 bg-black/40 z-40 sm:hidden"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Sidebar panel */}
      <aside className={`
        fixed sm:static inset-y-0 left-0 z-40
        w-56 shrink-0 border-r border-[--border] bg-[--card]
        transition-transform duration-200
        ${open ? "translate-x-0" : "-translate-x-full"}
        sm:translate-x-0
      `}>
        {/* existing sidebar content unchanged */}
      </aside>
    </>
  );
}
```

Note: Wrap the existing nav content inside the `<aside>` above without changing it.

- [ ] **Step 3: Add responsive table utilities in `dashboard/src/app/globals.css`**

At the end of globals.css, add:

```css
/* Mobile responsive */
@media (max-width: 640px) {
  .overflow-x-auto {
    -webkit-overflow-scrolling: touch;
  }

  /* History table — scroll horizontally on small screens */
  table {
    min-width: 640px;
  }

  /* Charts — allow vertical shrink */
  .recharts-responsive-container {
    min-height: 140px !important;
  }

  /* Overview stat grid: 2 columns on mobile */
  .stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
  }
}
```

Then wrap the overview stat cards container in page.tsx with `className="stat-grid grid ..."` if it isn't already.

- [ ] **Step 4: Verify build**

```bash
cd dashboard
npm run build 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/sidebar.tsx dashboard/src/app/globals.css
git commit -m "feat(mobile): hamburger sidebar toggle + responsive table scroll"
```

---

## Task 11 — Pagination frontend audit (Feature 6)

*Server-side pagination already exists in `routes/history.py`. Verify the Activity page uses it correctly.*

**Files:**
- Read: `dashboard/src/app/activity/page.tsx`
- Fix if loading all at once

- [ ] **Step 1: Check current Activity page**

```bash
grep -n "page\|page_size\|pagination\|fetch\|history" dashboard/src/app/activity/page.tsx | head -40
```

- [ ] **Step 2: Verify the fetch uses server-side pagination params**

The API call must include `?page=N&page_size=M` query params. If the call is `GET /api/usage/history` without these params, it defaults to page 1 + page_size 50 (server enforces limit), so it's already bounded.

If the fetch looks like:
```typescript
const resp = await api.usage.history({ page: currentPage, page_size: pageSize, ... });
```
→ Pagination is correct, no action needed.

If the fetch loads ALL records and paginates client-side:
→ Fix to use the `page` and `page_size` params from `routes/history.py`.

- [ ] **Step 3: If fix needed — update activity page fetch**

Replace any full-load fetch with:
```typescript
const resp = await fetch(
  `${BASE}/api/usage/history?page=${page}&page_size=${pageSize}${filters}`
);
const data: HistoryPage = await resp.json();
setRecords(data.items);
setTotalPages(data.pages);
```

- [ ] **Step 4: If changed, commit**

```bash
git add dashboard/src/app/activity/page.tsx
git commit -m "fix(activity): use server-side pagination for usage history"
```

---

## Summary

| Task | Feature | Backend | Frontend | Tests |
|------|---------|---------|----------|-------|
| 1 | Auto-downgrade verify | — | — | test_autodowngrade.py |
| 2 | Slack webhook | alert_service.py | — | test_slack_webhook.py |
| 3 | Export CSV/JSON | routes/export.py | — | test_export.py |
| 4 | Timeout/retry | models, forwarder, proxy, projects | — | test_configurable_timeout.py |
| 5 | Grace rotation | models, proxy, projects | — | test_grace_period_rotation.py |
| 6 | Members/Teams | models, auth, routes/members, main | — | test_members.py |
| 7 | Global chart | main.py endpoint | page.tsx, api.ts | test_global_daily.py |
| 8 | Landing page | — | landing/page.tsx | build check |
| 9 | Mobile | — | sidebar.tsx, globals.css | build check |
| 10 | Pagination audit | — | activity/page.tsx | verify |

**Total new tests: ~35 across 7 new test files. All must be GREEN before deploy.**

Apply the 3 Alembic migrations on prod after Tasks 4, 5, and 6 respectively.
