"""TDD RED — Export endpoint: GET /api/usage/export returns CSV or JSON."""
import csv
import io
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
        project_id=proj["id"],
        provider="openai",
        model="gpt-4o",
        tokens_in=100,
        tokens_out=50,
        cost_usd=0.01,
        created_at=datetime.now(),
    ))
    test_db.add(Usage(
        project_id=proj["id"],
        provider="anthropic",
        model="claude-sonnet-4-6",
        tokens_in=200,
        tokens_out=80,
        cost_usd=0.02,
        created_at=datetime.now(),
    ))
    test_db.commit()
    return proj


class TestExportEndpoint:
    @pytest.mark.asyncio
    async def test_export_csv_returns_csv_content_type(self, client, seeded_db):
        r = await client.get("/api/usage/export?format=csv")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]

    @pytest.mark.asyncio
    async def test_export_csv_has_header_and_rows(self, client, seeded_db):
        r = await client.get("/api/usage/export?format=csv")
        assert r.status_code == 200
        reader = csv.DictReader(io.StringIO(r.text))
        rows = list(reader)
        assert len(rows) == 2
        assert reader.fieldnames is not None
        for field in ("id", "provider", "model", "cost_usd", "created_at"):
            assert field in reader.fieldnames, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_export_csv_filter_by_project(self, client, test_db):
        # Create two projects with one Usage each
        r1 = await client.post("/api/projects", json={"name": "proj-export-1"})
        r2 = await client.post("/api/projects", json={"name": "proj-export-2"})
        p1 = r1.json()
        p2 = r2.json()

        test_db.add(Usage(
            project_id=p1["id"],
            provider="openai",
            model="gpt-4o",
            tokens_in=10,
            tokens_out=5,
            cost_usd=0.001,
            created_at=datetime.now(),
        ))
        test_db.add(Usage(
            project_id=p2["id"],
            provider="anthropic",
            model="claude-haiku-4-5",
            tokens_in=20,
            tokens_out=10,
            cost_usd=0.002,
            created_at=datetime.now(),
        ))
        test_db.commit()

        r = await client.get(f"/api/usage/export?format=csv&project_id={p1['id']}")
        assert r.status_code == 200
        reader = csv.DictReader(io.StringIO(r.text))
        rows = list(reader)
        assert len(rows) == 1
        assert int(rows[0]["project_id"]) == p1["id"]

    @pytest.mark.asyncio
    async def test_export_json_returns_list(self, client, seeded_db):
        r = await client.get("/api/usage/export?format=json")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 2
        for item in data:
            assert "provider" in item
            assert "cost_usd" in item

    @pytest.mark.asyncio
    async def test_export_unknown_format_returns_400(self, client):
        r = await client.get("/api/usage/export?format=xml")
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_export_invalid_date_returns_422(self, client):
        resp = await client.get("/api/usage/export?format=csv&date_from=not-a-date")
        assert resp.status_code == 422
