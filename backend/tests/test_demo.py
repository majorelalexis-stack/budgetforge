import pytest
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.mark.asyncio
async def test_demo_projects_returns_list():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/demo/projects")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 3
    assert "name" in data[0]
    assert "budget_usd" in data[0]


@pytest.mark.asyncio
async def test_demo_projects_has_four_projects():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/demo/projects")
    data = res.json()
    assert len(data) == 4


@pytest.mark.asyncio
async def test_demo_projects_has_exceeded_project():
    """At least one project must be at >= 100% budget (exceeded)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/demo/projects")
    data = res.json()
    exceeded = [p for p in data if p["used_usd"] >= p["budget_usd"]]
    assert len(exceeded) >= 1


@pytest.mark.asyncio
async def test_demo_projects_has_near_limit_project():
    """At least one project must be at >= 80% but < 100% budget (at risk)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/demo/projects")
    data = res.json()
    at_risk = [p for p in data if 80 <= (p["used_usd"] / p["budget_usd"] * 100) < 100]
    assert len(at_risk) >= 1


@pytest.mark.asyncio
async def test_demo_projects_schema():
    """Every project must have required fields."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/demo/projects")
    data = res.json()
    required_fields = {"name", "budget_usd", "used_usd", "pct_used", "action"}
    for project in data:
        for field in required_fields:
            assert field in project, f"Missing field {field!r} in project {project.get('name')}"


@pytest.mark.asyncio
async def test_demo_usage_summary():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/demo/usage/summary")
    assert res.status_code == 200
    data = res.json()
    assert "total_cost_usd" in data
    assert "total_calls" in data


@pytest.mark.asyncio
async def test_demo_usage_summary_schema():
    """Summary must have all expected fields with correct types."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/demo/usage/summary")
    data = res.json()
    assert isinstance(data["total_cost_usd"], float)
    assert isinstance(data["total_calls"], int)
    assert "projects_count" in data
    assert "at_risk_count" in data
    assert "exceeded_count" in data


@pytest.mark.asyncio
async def test_demo_usage_daily():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/demo/usage/daily")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 30
    assert "date" in data[0]
    assert "spend" in data[0]


@pytest.mark.asyncio
async def test_demo_usage_daily_deterministic():
    """Daily data must be deterministic (same result on two calls)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res1 = await client.get("/api/demo/usage/daily")
        res2 = await client.get("/api/demo/usage/daily")
    assert res1.json() == res2.json()


@pytest.mark.asyncio
async def test_demo_usage_daily_dates_are_sorted():
    """Daily entries must be sorted chronologically."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/demo/usage/daily")
    data = res.json()
    dates = [entry["date"] for entry in data]
    assert dates == sorted(dates)


@pytest.mark.asyncio
async def test_demo_usage_daily_spend_values():
    """All spend values must be non-negative floats."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/demo/usage/daily")
    data = res.json()
    for entry in data:
        assert isinstance(entry["spend"], (int, float))
        assert entry["spend"] >= 0
