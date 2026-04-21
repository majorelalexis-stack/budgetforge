import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

_project_locks: dict[int, asyncio.Lock] = {}
_registry_lock = asyncio.Lock()


async def _get_lock(project_id: int) -> asyncio.Lock:
    async with _registry_lock:
        if project_id not in _project_locks:
            _project_locks[project_id] = asyncio.Lock()
        return _project_locks[project_id]


@asynccontextmanager
async def budget_lock(project_id: int) -> AsyncIterator[None]:
    """Serialise le check budget + pre-bill pour un projet donné.

    Empêche la race condition TOCTOU: deux requêtes concurrentes ne peuvent pas
    toutes les deux passer le check budget avant que la première ait pré-facturé.
    Le lock est relâché avant l'appel LLM (long) — seule la phase critique est sérialisée.
    Note: efficace pour un déploiement single-process (uvicorn --workers 1).
    """
    lock = await _get_lock(project_id)
    async with lock:
        yield
