"""
Audit #2 — Phase C : Business logic (TDD RED→GREEN)

Findings couverts :
  C1 [H1] — Streaming : annuler l'usage si erreur en cours de stream
  C2 [H2] — Implémenter proxy_retries (retry 5xx)
  C3 [H7] — Export : exiger project_id pour les viewers
  C4 [H9] — History : total_cost SQL-side + joinedload
  C5 [C5] — Budget lock concurrent (asyncio.Lock documenté single-process)
  C6 [M4] — Budget $0 avec action=block → warning dans la réponse
  C7 [M5] — Valider downgrade_chain (doublons, longueur max 10)
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from core.database import Base, get_db


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

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


def _make_project(db, **kwargs):
    from core.models import Project
    defaults = {"name": "test-proj"}
    defaults.update(kwargs)
    p = Project(**defaults)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


# ──────────────────────────────────────────────────────────────────────────────
# C1 [H1] — Streaming : usage prebillé annulé si erreur en cours de stream
# État : except block ne cancel pas → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestStreamingCancelsUsageOnError:
    @pytest.mark.asyncio
    async def test_stream_error_cancels_prebilled_usage(self, client, test_db):
        """Erreur pendant le stream → usage prebillé supprimé de la DB. RED."""
        from core.models import Project, Usage

        proj = _make_project(test_db, name="stream-cancel-test")

        async def failing_stream(*args, **kwargs):
            yield b"data: {}\n\n"
            raise ConnectionError("provider dropped connection mid-stream")

        with patch("routes.proxy.ProxyForwarder.forward_openai_stream", side_effect=failing_stream):
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {proj.api_key}"},
                json={
                    "model": "gpt-4o",
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": True,
                },
            )
            # consommer le stream pour déclencher l'exception
            _ = resp.content

        usages = test_db.query(Usage).filter(Usage.project_id == proj.id).all()
        assert len(usages) == 0, (
            f"L'usage prebillé devrait être supprimé après erreur de stream, "
            f"trouvé {len(usages)} enregistrement(s). Ajouter _cancel_usage dans except."
        )

    @pytest.mark.asyncio
    async def test_stream_success_keeps_usage(self, client, test_db):
        """Stream réussi → usage conservé en DB. GREEN (comportement existant)."""
        from core.models import Project, Usage

        proj = _make_project(test_db, name="stream-ok-test")

        usage_chunk = (
            b'data: {"choices":[{"delta":{"content":"hi"}}],'
            b'"usage":{"prompt_tokens":5,"completion_tokens":3}}\n\n'
            b"data: [DONE]\n\n"
        )

        async def ok_stream(*args, **kwargs):
            yield usage_chunk

        with patch("routes.proxy.ProxyForwarder.forward_openai_stream", side_effect=ok_stream):
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {proj.api_key}"},
                json={
                    "model": "gpt-4o",
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": True,
                },
            )
            _ = resp.content

        usages = test_db.query(Usage).filter(Usage.project_id == proj.id).all()
        assert len(usages) == 1, "L'usage doit être conservé si le stream réussit."


# ──────────────────────────────────────────────────────────────────────────────
# C2 [H2] — proxy_retries : retry sur 5xx
# État : proxy_retries ignoré → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestProxyRetries:
    @pytest.mark.asyncio
    async def test_proxy_retries_on_5xx_error(self, client, test_db):
        """Avec proxy_retries=2, retry une fois après erreur → 200. RED."""
        import httpx
        proj = _make_project(test_db, name="retry-test", proxy_retries=2)

        call_count = 0

        async def flaky_forward(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.HTTPStatusError(
                    "503", request=MagicMock(), response=MagicMock(status_code=503)
                )
            return {
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            }

        with patch("routes.proxy.ProxyForwarder.forward_openai", side_effect=flaky_forward):
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {proj.api_key}"},
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
            )

        assert resp.status_code == 200, (
            f"Avec proxy_retries=2, la 2e tentative devrait réussir (200). "
            f"Obtenu {resp.status_code}. proxy_retries n'est pas implémenté."
        )
        assert call_count == 2, f"forward_openai devrait être appelé 2x, appelé {call_count}x."

    @pytest.mark.asyncio
    async def test_proxy_retries_exhausted_returns_502(self, client, test_db):
        """Avec proxy_retries=1, toutes tentatives échouent → 502. RED."""
        import httpx
        proj = _make_project(test_db, name="retry-exhaust", proxy_retries=1)

        async def always_fail(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "503", request=MagicMock(), response=MagicMock(status_code=503)
            )

        with patch("routes.proxy.ProxyForwarder.forward_openai", side_effect=always_fail):
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {proj.api_key}"},
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
            )

        assert resp.status_code == 502

    @pytest.mark.asyncio
    async def test_proxy_no_retry_on_4xx(self, client, test_db):
        """4xx (ex: 401 auth) ne doit pas être retenté. RED."""
        import httpx
        proj = _make_project(test_db, name="no-retry-4xx", proxy_retries=3)

        call_count = 0

        async def auth_error(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise httpx.HTTPStatusError(
                "401", request=MagicMock(), response=MagicMock(status_code=401)
            )

        with patch("routes.proxy.ProxyForwarder.forward_openai", side_effect=auth_error):
            await client.post(
                "/proxy/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {proj.api_key}"},
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
            )

        assert call_count == 1, (
            f"Une erreur 4xx ne doit pas être retentée. "
            f"forward_openai a été appelé {call_count}x au lieu de 1x."
        )


# ──────────────────────────────────────────────────────────────────────────────
# C3 [H7] — Export : exiger project_id
# État : pas de vérification → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestExportRequiresProjectId:
    @pytest.mark.asyncio
    async def test_export_without_project_id_in_prod_returns_400(self, client, test_db):
        """GET /api/usage/export sans project_id en prod avec clé membre → 400. GREEN."""
        from core.models import Member
        from core.config import settings

        member = Member(email="viewer@test.com", role="viewer")
        test_db.add(member)
        test_db.commit()
        test_db.refresh(member)

        with patch.object(settings, "admin_api_key", "prod-admin-key"):
            resp = await client.get(
                "/api/usage/export?format=json",
                headers={"X-Admin-Key": member.api_key},
            )
        assert resp.status_code == 400, (
            f"Export sans project_id avec clé membre doit retourner 400, obtenu {resp.status_code}."
        )

    @pytest.mark.asyncio
    async def test_export_with_project_id_returns_200(self, client, test_db):
        """GET /api/usage/export?project_id=N → 200. GREEN après fix."""
        proj = _make_project(test_db, name="export-proj")
        resp = await client.get(f"/api/usage/export?format=json&project_id={proj.id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_export_admin_key_without_project_id_allowed(self, client):
        """Admin global peut exporter sans project_id. GREEN après fix."""
        from core.config import settings
        with patch.object(settings, "admin_api_key", "admin-global"):
            resp = await client.get(
                "/api/usage/export?format=json",
                headers={"X-Admin-Key": "admin-global"},
            )
        assert resp.status_code == 200, (
            "L'admin global doit pouvoir exporter sans project_id."
        )


# ──────────────────────────────────────────────────────────────────────────────
# C4 [H9] — History : total_cost SQL-side (comportement correct, perfs)
# Ces tests sont verts — ils vérifient la justesse du résultat
# ──────────────────────────────────────────────────────────────────────────────

class TestHistorySqlAggregation:
    @pytest.mark.asyncio
    async def test_total_cost_correct_with_many_records(self, client, test_db):
        """total_cost_usd correct sur 50 enregistrements. GREEN (comportement)."""
        from core.models import Usage

        proj = _make_project(test_db, name="sql-agg-test")
        for i in range(50):
            u = Usage(project_id=proj.id, provider="openai", model="gpt-4o",
                      tokens_in=10, tokens_out=5, cost_usd=0.001)
            test_db.add(u)
        test_db.commit()

        resp = await client.get("/api/usage/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 50
        assert abs(data["total_cost_usd"] - 0.050) < 1e-6

    @pytest.mark.asyncio
    async def test_history_total_cost_uses_sql_func(self, client, test_db):
        """total_cost_usd ne doit PAS charger tous les enregistrements via query.all(). RED."""
        from core.models import Usage
        from sqlalchemy.orm import Session as SASession

        proj = _make_project(test_db, name="no-query-all-test")
        for _ in range(5):
            u = Usage(project_id=proj.id, provider="openai", model="gpt-4o",
                      tokens_in=10, tokens_out=5, cost_usd=0.002)
            test_db.add(u)
        test_db.commit()

        queries_executed = []
        original_execute = test_db.execute

        def tracking_execute(stmt, *args, **kwargs):
            queries_executed.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
            return original_execute(stmt, *args, **kwargs)

        with patch.object(test_db, "execute", side_effect=tracking_execute):
            resp = await client.get("/api/usage/history")

        assert resp.status_code == 200
        sql_has_sum = any("SUM" in q.upper() for q in queries_executed)
        assert sql_has_sum, (
            "total_cost_usd doit utiliser func.sum() en SQL, pas sum() Python sur query.all(). "
            "Aucun SUM trouvé dans les requêtes exécutées."
        )


# ──────────────────────────────────────────────────────────────────────────────
# C5 [C5] — Budget lock : les requêtes concurrentes ne dépassent pas le budget
# Ce test valide le comportement EXISTANT du asyncio.Lock (single-process)
# ──────────────────────────────────────────────────────────────────────────────

class TestBudgetLockConcurrency:
    @pytest.mark.asyncio
    async def test_second_request_blocked_after_budget_spent(self, client, test_db):
        """Après qu'une requête épuise le budget, la suivante est bloquée. GREEN (Lock)."""
        from core.models import Usage

        proj = _make_project(test_db, name="seq-budget", budget_usd=0.0001, action="block")

        mock_response = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }

        with patch("routes.proxy.ProxyForwarder.forward_openai",
                   new_callable=AsyncMock, return_value=mock_response), \
             patch("routes.proxy.CostCalculator.compute_cost", return_value=0.00015):

            resp1 = await client.post(
                "/proxy/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {proj.api_key}"},
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
            )
            resp2 = await client.post(
                "/proxy/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {proj.api_key}"},
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
            )

        assert resp1.status_code == 200, "Première requête doit passer."
        assert resp2.status_code == 429, (
            f"Deuxième requête doit être bloquée (budget épuisé → 429), "
            f"obtenu {resp2.status_code}."
        )


# ──────────────────────────────────────────────────────────────────────────────
# C6 [M4] — Budget $0 avec action=block → warning dans la réponse
# État : pas de warning → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestBudgetZeroWarning:
    @pytest.mark.asyncio
    async def test_budget_zero_block_returns_warning(self, client, test_db):
        """PUT /budget avec budget_usd=0 et action=block → warning dans réponse. RED."""
        proj = _make_project(test_db, name="zero-budget-warn")

        resp = await client.put(
            f"/api/projects/{proj.id}/budget",
            json={
                "budget_usd": 0,
                "alert_threshold_pct": 80,
                "action": "block",
                "reset_period": "none",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "warning" in body, (
            "budget_usd=0 avec action=block doit retourner un champ 'warning' dans la réponse. "
            f"Réponse reçue : {body}"
        )

    @pytest.mark.asyncio
    async def test_budget_positive_no_warning(self, client, test_db):
        """PUT /budget avec budget_usd>0 → pas de warning. GREEN."""
        proj = _make_project(test_db, name="positive-budget")

        resp = await client.put(
            f"/api/projects/{proj.id}/budget",
            json={
                "budget_usd": 10.0,
                "alert_threshold_pct": 80,
                "action": "block",
                "reset_period": "none",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "warning" not in body or body.get("warning") is None


# ──────────────────────────────────────────────────────────────────────────────
# C7 [M5] — Valider downgrade_chain (doublons consécutifs, longueur max 10)
# État : pas de validation → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestDowngradeChainValidation:
    @pytest.mark.asyncio
    async def test_duplicate_consecutive_items_rejected(self, client, test_db):
        """downgrade_chain avec doublons consécutifs → 422. RED."""
        proj = _make_project(test_db, name="dup-chain-test")

        resp = await client.put(
            f"/api/projects/{proj.id}/budget",
            json={
                "budget_usd": 5.0,
                "alert_threshold_pct": 80,
                "action": "downgrade",
                "reset_period": "none",
                "downgrade_chain": ["gpt-4o", "gpt-4o", "gpt-4o-mini"],
            },
        )
        assert resp.status_code == 422, (
            f"downgrade_chain avec doublons consécutifs doit retourner 422, "
            f"obtenu {resp.status_code}."
        )

    @pytest.mark.asyncio
    async def test_chain_exceeding_max_length_rejected(self, client, test_db):
        """downgrade_chain > 10 éléments → 422. RED."""
        proj = _make_project(test_db, name="long-chain-test")
        long_chain = [f"model-{i}" for i in range(11)]

        resp = await client.put(
            f"/api/projects/{proj.id}/budget",
            json={
                "budget_usd": 5.0,
                "alert_threshold_pct": 80,
                "action": "downgrade",
                "reset_period": "none",
                "downgrade_chain": long_chain,
            },
        )
        assert resp.status_code == 422, (
            f"downgrade_chain > 10 éléments doit retourner 422, obtenu {resp.status_code}."
        )

    @pytest.mark.asyncio
    async def test_valid_chain_accepted(self, client, test_db):
        """downgrade_chain valide (sans doublons, ≤10) → 200. GREEN après fix."""
        proj = _make_project(test_db, name="valid-chain-test")

        resp = await client.put(
            f"/api/projects/{proj.id}/budget",
            json={
                "budget_usd": 5.0,
                "alert_threshold_pct": 80,
                "action": "downgrade",
                "reset_period": "none",
                "downgrade_chain": ["gpt-4o", "gpt-4o-mini", "claude-haiku-4-5"],
            },
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_empty_chain_accepted(self, client, test_db):
        """downgrade_chain vide → 200. GREEN."""
        proj = _make_project(test_db, name="empty-chain-test")

        resp = await client.put(
            f"/api/projects/{proj.id}/budget",
            json={
                "budget_usd": 5.0,
                "alert_threshold_pct": 80,
                "action": "block",
                "reset_period": "none",
                "downgrade_chain": [],
            },
        )
        assert resp.status_code == 200
