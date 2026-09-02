"""0001_initial_schema: Core DeepSearch storage schema (§43, DS-17).

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-02 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Projects table
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 2. Jobs table
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id"),
            nullable=True,
        ),
        sa.Column(
            "status", sa.String(length=50), nullable=False, server_default="RUNNING"
        ),
        sa.Column(
            "mode", sa.String(length=50), nullable=False, server_default="balanced"
        ),
        sa.Column("pages_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bytes_downloaded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "browser_escalation_ratio",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 3. Pages table
    op.create_table(
        "pages",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "job_id",
            sa.String(length=36),
            sa.ForeignKey("jobs.id"),
            nullable=False,
        ),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("strategy_used", sa.String(length=50), nullable=False),
        sa.Column("raw_content_hash", sa.String(length=64), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 4. Records table
    op.create_table(
        "records",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "page_id",
            sa.String(length=36),
            sa.ForeignKey("pages.id"),
            nullable=False,
        ),
        sa.Column("schema_name", sa.String(length=100), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 5. Errors table
    op.create_table(
        "errors",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "job_id",
            sa.String(length=36),
            sa.ForeignKey("jobs.id"),
            nullable=False,
        ),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("errors")
    op.drop_table("records")
    op.drop_table("pages")
    op.drop_table("jobs")
    op.drop_table("projects")
