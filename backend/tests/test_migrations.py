"""TDD RED — Alembic migrations: ensure migrations exist and apply cleanly."""
import pytest
import os
from pathlib import Path


def test_alembic_ini_exists():
    """alembic.ini must exist at backend root."""
    root = Path(__file__).parent.parent
    assert (root / "alembic.ini").exists()


def test_alembic_versions_not_empty():
    """At least one migration file must exist in alembic/versions/."""
    root = Path(__file__).parent.parent
    versions = list((root / "alembic" / "versions").glob("*.py"))
    assert len(versions) >= 1, "No migration files found"


def test_alembic_env_has_target_metadata():
    """env.py must import Base.metadata as target_metadata."""
    root = Path(__file__).parent.parent
    env_content = (root / "alembic" / "env.py").read_text()
    assert "target_metadata = Base.metadata" in env_content


def test_migration_upgrade_applies_cleanly(tmp_path):
    """Running alembic upgrade head on a fresh DB must succeed."""
    import subprocess, sys
    python = sys.executable
    db_path = tmp_path / "test_migrate.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"

    root = Path(__file__).parent.parent
    result = subprocess.run(
        [python, "-m", "alembic", "upgrade", "head"],
        cwd=str(root),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"


def test_migration_downgrade_applies_cleanly(tmp_path):
    """Running alembic downgrade base after upgrade must succeed."""
    import subprocess, sys
    python = sys.executable
    db_path = tmp_path / "test_migrate_down.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"

    root = Path(__file__).parent.parent
    subprocess.run(
        [python, "-m", "alembic", "upgrade", "head"],
        cwd=str(root), capture_output=True, env=env,
    )
    result = subprocess.run(
        [python, "-m", "alembic", "downgrade", "base"],
        cwd=str(root),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"
