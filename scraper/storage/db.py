"""Database initialization and session handling (§43, DS-17)."""

import os
from pathlib import Path
from typing import Optional
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from scraper.config import settings


def get_alembic_config(
    config_path: Optional[str] = None, database_url: Optional[str] = None
) -> Config:
    """Build Alembic Config object pointing to the canonical migrations directory."""
    if config_path is None:
        root = Path(__file__).resolve().parent.parent.parent
        ini_path = root / "alembic.ini"
        if ini_path.exists():
            cfg = Config(str(ini_path))
        else:
            cfg = Config()
            cfg.set_main_option("script_location", str(root / "migrations"))
    else:
        cfg = Config(config_path)

    url = database_url or settings.database_url
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def run_migrations(
    target_revision: str = "head",
    config_path: Optional[str] = None,
    database_url: Optional[str] = None,
) -> None:
    """Apply Alembic migrations up to target_revision."""
    cfg = get_alembic_config(config_path, database_url)
    command.upgrade(cfg, target_revision)


def downgrade_migrations(
    target_revision: str = "-1",
    config_path: Optional[str] = None,
    database_url: Optional[str] = None,
) -> None:
    """Rollback Alembic migrations down to target_revision."""
    cfg = get_alembic_config(config_path, database_url)
    command.downgrade(cfg, target_revision)


engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def init_db(database_url: Optional[str] = None) -> None:
    """Initialize database by applying canonical Alembic migrations."""
    url = database_url or settings.database_url
    if "sqlite" in url and ":///" in url:
        db_path = url.split(":///", 1)[1]
        if db_path and not db_path.startswith(":memory:"):
            parent_dir = os.path.dirname(db_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
    run_migrations(target_revision="head", database_url=database_url)
