import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scraper.config import settings
from scraper.storage.models import Base

# Alembic Config object
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Retrieve database URL from alembic config or application settings."""
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        url = settings.database_url
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    # Offline mode needs a sync-compatible dialect URL for rendering SQL scripts
    sync_url = url.replace("sqlite+aiosqlite://", "sqlite://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Execute migrations within an active database connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations(connectable=None) -> None:
    """Run migrations asynchronously using an AsyncEngine."""
    if connectable is None:
        url = get_url()
        connectable = create_async_engine(
            url,
            poolclass=pool.NullPool,
        )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = config.attributes.get("connection", None)

    if connectable is not None:
        if isinstance(connectable, Connection):
            do_run_migrations(connectable)
        else:
            # AsyncConnection
            asyncio.run(connectable.run_sync(do_run_migrations))
        return

    url = get_url()
    if "+aiosqlite" in url or "+asyncpg" in url or "async" in url:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # If already inside a running event loop in current thread, create task
            # or run via thread executor
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool_exec:
                pool_exec.submit(lambda: asyncio.run(run_async_migrations())).result()
        else:
            asyncio.run(run_async_migrations())
    else:
        from sqlalchemy import create_engine

        sync_engine = create_engine(url, poolclass=pool.NullPool)
        with sync_engine.connect() as connection:
            do_run_migrations(connection)
        sync_engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
