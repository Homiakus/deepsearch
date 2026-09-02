"""Unit tests for Storage & Migrations single source of truth (§DS-17)."""

import inspect as py_inspect

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import scraper.storage.db as storage_db
from scraper.config import settings
from scraper.storage.db import (
    downgrade_migrations,
    get_alembic_config,
    init_db,
    run_migrations,
)
from scraper.storage.models import (
    Base,
    ErrorModel,
    JobModel,
    PageModel,
    ProjectModel,
    RecordModel,
)


@pytest.mark.asyncio
async def test_default_profile_local_first_no_external_services():
    """Verify that default settings use local-first SQLite and filesystem without external dependencies."""
    assert "sqlite" in settings.database_url
    assert settings.cas_backend == "local"
    assert settings.distributed_queue_backend == "memory"


@pytest.mark.asyncio
async def test_no_create_all_in_storage_db():
    """Verify that create_all is eliminated as a parallel migration mechanism (§DS-17)."""
    src = py_inspect.getsource(storage_db)
    assert "create_all" not in src, "create_all must not be used in storage/db.py"


@pytest.mark.asyncio
async def test_alembic_migration_lifecycle(tmp_path):
    """Test full migration lifecycle: upgrade -> downgrade -> re-upgrade on clean DB."""
    db_file = tmp_path / "test_lifecycle.db"
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"

    # 1. Run migrations up to head
    await init_db(database_url=db_url)

    # Inspect tables
    sync_url = f"sqlite:///{db_file.as_posix()}"
    sync_engine = sa.create_engine(sync_url)
    with sync_engine.connect() as conn:
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())

    expected_tables = {
        "projects",
        "jobs",
        "pages",
        "records",
        "errors",
        "alembic_version",
    }
    assert expected_tables.issubset(tables)

    # 2. Downgrade to base
    downgrade_migrations(target_revision="base", database_url=db_url)

    with sync_engine.connect() as conn:
        inspector = inspect(conn)
        tables_after_down = set(inspector.get_table_names())

    # User tables must be dropped; only alembic_version might remain
    assert not {"projects", "jobs", "pages", "records", "errors"}.intersection(
        tables_after_down
    )

    # 3. Re-upgrade to head
    run_migrations(target_revision="head", database_url=db_url)

    with sync_engine.connect() as conn:
        inspector = inspect(conn)
        tables_reup = set(inspector.get_table_names())

    assert expected_tables.issubset(tables_reup)
    sync_engine.dispose()


@pytest.mark.asyncio
async def test_orm_and_migration_schema_diff_is_empty(tmp_path):
    """Verify zero schema diff between SQLAlchemy Base.metadata and migrated database."""
    db_file = tmp_path / "test_schemadiff.db"
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"

    await init_db(database_url=db_url)

    sync_url = f"sqlite:///{db_file.as_posix()}"
    sync_engine = sa.create_engine(sync_url)

    with sync_engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"render_as_batch": True})
        diff = compare_metadata(ctx, Base.metadata)

    # Difference list must be empty
    assert diff == [], f"Detected unexpected schema diff: {diff}"
    sync_engine.dispose()


@pytest.mark.asyncio
async def test_orm_crud_on_migrated_db(tmp_path):
    """Verify ORM models function properly against database created exclusively via migrations."""
    db_file = tmp_path / "test_crud.db"
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"

    await init_db(database_url=db_url)

    test_engine = create_async_engine(db_url)
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        # Create project
        proj = ProjectModel(
            id="proj-123",
            name="DeepSearch Research",
            description="Autonomous Crawl Project",
        )
        session.add(proj)

        # Create job
        job = JobModel(
            id="job-456",
            project_id="proj-123",
            status="RUNNING",
            mode="balanced",
            pages_processed=1,
            bytes_downloaded=1024,
            browser_escalation_ratio=0.25,
        )
        session.add(job)

        # Create page
        page = PageModel(
            id="page-789",
            job_id="job-456",
            url="https://example.com/paper.html",
            canonical_url="https://example.com/paper",
            status_code=200,
            strategy_used="http_fast",
            raw_content_hash="a1b2c3d4e5f67890",
            quality_score=0.95,
        )
        session.add(page)

        # Create record
        rec = RecordModel(
            id="rec-001",
            page_id="page-789",
            schema_name="academic_article",
            data={"title": "Adaptive Systems", "authors": ["Alice", "Bob"]},
        )
        session.add(rec)

        # Create error
        err = ErrorModel(
            id="err-001",
            job_id="job-456",
            url="https://example.com/broken.html",
            category="HTTP_404",
            error_message="Resource not found",
        )
        session.add(err)

        await session.commit()

    # Query back in a new session
    async with session_factory() as session:
        queried_proj = await session.get(ProjectModel, "proj-123")
        assert queried_proj is not None
        assert queried_proj.name == "DeepSearch Research"

        queried_job = await session.get(JobModel, "job-456")
        assert queried_job is not None
        assert queried_job.status == "RUNNING"
        assert queried_job.pages_processed == 1

        queried_page = await session.get(PageModel, "page-789")
        assert queried_page is not None
        assert queried_page.status_code == 200

        queried_rec = await session.get(RecordModel, "rec-001")
        assert queried_rec is not None
        assert queried_rec.data["title"] == "Adaptive Systems"

        queried_err = await session.get(ErrorModel, "err-001")
        assert queried_err is not None
        assert queried_err.category == "HTTP_404"

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_alembic_config_custom_parameters():
    """Verify get_alembic_config handles explicit database URLs correctly."""
    cfg = get_alembic_config(database_url="sqlite+aiosqlite:///custom.db")
    assert cfg.get_main_option("sqlalchemy.url") == "sqlite+aiosqlite:///custom.db"
