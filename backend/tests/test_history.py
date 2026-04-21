"""TDD RED — Usage history endpoint with pagination + filtering."""
import pytest
from datetime import datetime, timedelta, timezone
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


def _make_project(db, name: str) -> Project:
    p = Project(name=name)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _make_usage(
    db,
    project: Project,
    *,
    provider: str = "openai",
    model: str = "gpt-4o",
    tokens_in: int = 100,
    tokens_out: int = 50,
    cost_usd: float = 0.001,
    created_at: datetime | None = None,
) -> Usage:
    u = Usage(
        project_id=project.id,
        provider=provider,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        created_at=created_at or datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


class TestHistoryEndpoint:
    @pytest.mark.asyncio
    async def test_history_empty_returns_valid_page(self, client):
        r = await client.get("/api/usage/history")
        assert r.status_code == 200
        data = r.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["page_size"] == 50
        assert data["pages"] == 0
        assert data["total_cost_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_history_item_has_required_fields(self, client, test_db):
        p = _make_project(test_db, "field-check")
        _make_usage(test_db, p, cost_usd=0.005)
        r = await client.get("/api/usage/history")
        assert r.status_code == 200
        item = r.json()["items"][0]
        assert "id" in item
        assert item["project_name"] == "field-check"
        assert item["provider"] == "openai"
        assert item["model"] == "gpt-4o"
        assert item["tokens_in"] == 100
        assert item["tokens_out"] == 50
        assert item["cost_usd"] == pytest.approx(0.005)
        assert "created_at" in item

    @pytest.mark.asyncio
    async def test_history_sorted_newest_first_by_default(self, client, test_db):
        p = _make_project(test_db, "sort-check")
        old_dt = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=3)
        new_dt = datetime.now(timezone.utc).replace(tzinfo=None)
        _make_usage(test_db, p, model="old-model", created_at=old_dt)
        _make_usage(test_db, p, model="new-model", created_at=new_dt)
        r = await client.get("/api/usage/history")
        items = r.json()["items"]
        assert items[0]["model"] == "new-model"
        assert items[1]["model"] == "old-model"

    @pytest.mark.asyncio
    async def test_history_pagination_page_size(self, client, test_db):
        p = _make_project(test_db, "page-size-check")
        for _ in range(7):
            _make_usage(test_db, p)
        r = await client.get("/api/usage/history?page=1&page_size=3")
        data = r.json()
        assert len(data["items"]) == 3
        assert data["total"] == 7
        assert data["pages"] == 3
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_history_pagination_page_2(self, client, test_db):
        p = _make_project(test_db, "page-2-check")
        for _ in range(7):
            _make_usage(test_db, p)
        r = await client.get("/api/usage/history?page=2&page_size=3")
        data = r.json()
        assert len(data["items"]) == 3
        assert data["page"] == 2

    @pytest.mark.asyncio
    async def test_history_pagination_last_page(self, client, test_db):
        p = _make_project(test_db, "last-page-check")
        for _ in range(7):
            _make_usage(test_db, p)
        r = await client.get("/api/usage/history?page=3&page_size=3")
        data = r.json()
        assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_history_filter_by_project_id(self, client, test_db):
        p1 = _make_project(test_db, "proj-alpha")
        p2 = _make_project(test_db, "proj-beta")
        _make_usage(test_db, p1, model="alpha-model")
        _make_usage(test_db, p2, model="beta-model")
        r = await client.get(f"/api/usage/history?project_id={p1.id}")
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["model"] == "alpha-model"

    @pytest.mark.asyncio
    async def test_history_filter_by_provider(self, client, test_db):
        p = _make_project(test_db, "provider-filter")
        _make_usage(test_db, p, provider="openai")
        _make_usage(test_db, p, provider="anthropic")
        _make_usage(test_db, p, provider="ollama")
        r = await client.get("/api/usage/history?provider=anthropic")
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["provider"] == "anthropic"

    @pytest.mark.asyncio
    async def test_history_filter_by_model(self, client, test_db):
        p = _make_project(test_db, "model-filter")
        _make_usage(test_db, p, model="gpt-4o")
        _make_usage(test_db, p, model="gpt-4o-mini")
        r = await client.get("/api/usage/history?model=gpt-4o-mini")
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["model"] == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_history_filter_date_from(self, client, test_db):
        p = _make_project(test_db, "date-from-filter")
        old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=3)
        recent = datetime.now(timezone.utc).replace(tzinfo=None)
        _make_usage(test_db, p, model="old", created_at=old)
        _make_usage(test_db, p, model="recent", created_at=recent)
        cutoff = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)).date().isoformat()
        r = await client.get(f"/api/usage/history?date_from={cutoff}")
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["model"] == "recent"

    @pytest.mark.asyncio
    async def test_history_filter_date_to(self, client, test_db):
        p = _make_project(test_db, "date-to-filter")
        old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=3)
        recent = datetime.now(timezone.utc).replace(tzinfo=None)
        _make_usage(test_db, p, model="old", created_at=old)
        _make_usage(test_db, p, model="recent", created_at=recent)
        cutoff = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)).date().isoformat()
        r = await client.get(f"/api/usage/history?date_to={cutoff}")
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["model"] == "old"

    @pytest.mark.asyncio
    async def test_history_total_cost_aggregated(self, client, test_db):
        p = _make_project(test_db, "total-cost-check")
        _make_usage(test_db, p, cost_usd=0.010)
        _make_usage(test_db, p, cost_usd=0.025)
        r = await client.get("/api/usage/history")
        data = r.json()
        assert data["total_cost_usd"] == pytest.approx(0.035)

    @pytest.mark.asyncio
    async def test_history_total_cost_respects_filters(self, client, test_db):
        p1 = _make_project(test_db, "cost-p1")
        p2 = _make_project(test_db, "cost-p2")
        _make_usage(test_db, p1, cost_usd=0.010)
        _make_usage(test_db, p2, cost_usd=0.050)
        r = await client.get(f"/api/usage/history?project_id={p1.id}")
        assert r.json()["total_cost_usd"] == pytest.approx(0.010)

    @pytest.mark.asyncio
    async def test_history_page_size_exceeds_max_returns_422(self, client):
        r = await client.get("/api/usage/history?page_size=500")
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_history_page_zero_returns_422(self, client):
        r = await client.get("/api/usage/history?page=0")
        assert r.status_code == 422
