"""TDD RED — Admin business stats : clients par plan, MRR, signups, calls."""
import pytest
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timedelta
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


class TestAdminStats:
    @pytest.mark.asyncio
    async def test_stats_returns_200(self, client):
        """GET /api/admin/stats → 200."""
        resp = await client.get("/api/admin/stats")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_stats_shape(self, client):
        """La réponse contient tous les champs attendus."""
        resp = await client.get("/api/admin/stats")
        body = resp.json()
        assert "clients_by_plan" in body
        assert "mrr_usd" in body
        assert "total_clients" in body
        assert "signups_last_30_days" in body
        assert "total_calls" in body
        assert "total_spend_usd" in body
        assert len(body["signups_last_30_days"]) == 30

    @pytest.mark.asyncio
    async def test_stats_clients_by_plan(self, client, test_db):
        """clients_by_plan compte correctement par plan."""
        from core.models import Project
        for i, plan in enumerate(["free", "free", "pro", "agency"]):
            test_db.add(Project(name=f"{plan}{i}@test.com", plan=plan,
                                stripe_customer_id=f"cus_{plan}{i}",
                                stripe_subscription_id=f"sub_{plan}{i}"))
        test_db.commit()

        resp = await client.get("/api/admin/stats")
        body = resp.json()
        assert body["clients_by_plan"]["free"] == 2
        assert body["clients_by_plan"]["pro"] == 1
        assert body["clients_by_plan"]["agency"] == 1
        assert body["total_clients"] == 4

    @pytest.mark.asyncio
    async def test_stats_mrr(self, client, test_db):
        """MRR = pro*29 + agency*79."""
        from core.models import Project
        test_db.add(Project(name="p@test.com", plan="pro",
                            stripe_customer_id="cus_p", stripe_subscription_id="sub_p"))
        test_db.add(Project(name="a@test.com", plan="agency",
                            stripe_customer_id="cus_a", stripe_subscription_id="sub_a"))
        test_db.commit()

        resp = await client.get("/api/admin/stats")
        body = resp.json()
        assert body["mrr_usd"] == 29 + 79

    @pytest.mark.asyncio
    async def test_stats_calls_and_spend(self, client, test_db):
        """total_calls et total_spend_usd agrègent bien les usages."""
        from core.models import Project, Usage
        proj = Project(name="u@test.com", plan="free",
                       stripe_customer_id="cus_u", stripe_subscription_id="sub_u")
        test_db.add(proj)
        test_db.commit()
        test_db.add(Usage(project_id=proj.id, provider="openai", model="gpt-4o",
                          tokens_in=100, tokens_out=50, cost_usd=0.05))
        test_db.add(Usage(project_id=proj.id, provider="anthropic", model="claude-sonnet-4-6",
                          tokens_in=200, tokens_out=100, cost_usd=0.10))
        test_db.commit()

        resp = await client.get("/api/admin/stats")
        body = resp.json()
        assert body["total_calls"] == 2
        assert abs(body["total_spend_usd"] - 0.15) < 1e-6

    @pytest.mark.asyncio
    async def test_stats_signups_last_30_days(self, client, test_db):
        """signups_last_30_days compte les projets créés par jour sur 30j."""
        from core.models import Project
        today = datetime.utcnow()
        proj1 = Project(name="s1@test.com", plan="free",
                        stripe_customer_id="cus_s1", stripe_subscription_id="sub_s1")
        proj1.created_at = today - timedelta(days=2)
        proj2 = Project(name="s2@test.com", plan="pro",
                        stripe_customer_id="cus_s2", stripe_subscription_id="sub_s2")
        proj2.created_at = today - timedelta(days=2)
        proj3 = Project(name="s3@test.com", plan="free",
                        stripe_customer_id="cus_s3", stripe_subscription_id="sub_s3")
        proj3.created_at = today - timedelta(days=40)  # hors fenêtre
        test_db.add_all([proj1, proj2, proj3])
        test_db.commit()

        resp = await client.get("/api/admin/stats")
        body = resp.json()
        daily = {d["date"]: d["count"] for d in body["signups_last_30_days"]}
        target = (today - timedelta(days=2)).date().isoformat()
        assert daily[target] == 2
        total_in_window = sum(d["count"] for d in body["signups_last_30_days"])
        assert total_in_window == 2  # proj3 hors fenêtre


class TestAdminStatsGrowth:
    @pytest.mark.asyncio
    async def test_stats_includes_client_growth(self, client):
        """admin/stats inclut client_growth (90 entrées)."""
        resp = await client.get("/api/admin/stats")
        body = resp.json()
        assert "client_growth" in body
        assert isinstance(body["client_growth"], list)
        assert len(body["client_growth"]) == 90

    @pytest.mark.asyncio
    async def test_stats_client_growth_is_cumulative(self, client, test_db):
        """client_growth est un running total cumulatif par jour."""
        from core.models import Project

        today = datetime.utcnow()
        p1 = Project(name="g1@test.com", plan="free",
                     stripe_customer_id="cus_g1", stripe_subscription_id="sub_g1")
        p1.created_at = today - timedelta(days=5)
        p2 = Project(name="g2@test.com", plan="pro",
                     stripe_customer_id="cus_g2", stripe_subscription_id="sub_g2")
        p2.created_at = today - timedelta(days=3)
        p3 = Project(name="g3@test.com", plan="agency",
                     stripe_customer_id="cus_g3", stripe_subscription_id="sub_g3")
        p3.created_at = today - timedelta(days=3)
        test_db.add_all([p1, p2, p3])
        test_db.commit()

        resp = await client.get("/api/admin/stats")
        body = resp.json()
        growth = {d["date"]: d["total"] for d in body["client_growth"]}

        day5 = (today - timedelta(days=5)).date().isoformat()
        day3 = (today - timedelta(days=3)).date().isoformat()
        day0 = today.date().isoformat()

        assert growth[day5] == 1   # p1 seulement
        assert growth[day3] == 3   # p1 + p2 + p3
        assert growth[day0] == 3   # pas de nouveaux
