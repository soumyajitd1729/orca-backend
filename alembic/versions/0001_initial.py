"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-31
"""
import uuid

import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

UUID = postgresql.UUID
JSONB = postgresql.JSONB
ENUM = sa.Enum


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "users",
        sa.Column("id", UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            ENUM("fisherman", "authority", "operator", name="user_role"),
            nullable=False,
        ),
        sa.Column(
            "preferred_language",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'en'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "data_source_health",
        sa.Column("id", UUID(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column(
            "priority", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "status",
            ENUM("live", "cached", "stale", "unavailable", name="source_status"),
            nullable=False,
            server_default=sa.text("'unavailable'"),
        ),
        sa.Column("last_fetch_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "conversations",
        sa.Column("id", UUID(), nullable=False),
        sa.Column("user_id", UUID(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_active_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "messages",
        sa.Column("id", UUID(), nullable=False),
        sa.Column("conversation_id", UUID(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", UUID(), nullable=False),
        sa.Column("conversation_id", UUID(), nullable=True),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("task_id", UUID(), nullable=True),
        sa.Column(
            "status",
            ENUM("pending", "running", "success", "failed", name="agent_run_status"),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "retries", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="SET NULL"
        ),
    )

    op.create_table(
        "evidence_items",
        sa.Column("id", UUID(), nullable=False),
        sa.Column("task_id", UUID(), nullable=True),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("variable", sa.String(length=128), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column(
            "unit", sa.String(length=32), nullable=False, server_default=sa.text("''")
        ),
        sa.Column("valid_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "confidence", sa.Float(), nullable=False, server_default=sa.text("0.0")
        ),
        sa.Column("url_ref", sa.String(length=1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "warnings",
        sa.Column("id", UUID(), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column(
            "severity",
            ENUM("low", "moderate", "high", "extreme", name="warning_severity"),
            nullable=False,
        ),
        sa.Column(Geometry("POLYGON", srid=4326), name="geometry", nullable=True),
        sa.Column("issued_by", sa.String(length=128), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "pfz_zones",
        sa.Column("id", UUID(), nullable=False),
        sa.Column(Geometry("POLYGON", srid=4326), name="geometry", nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("components", JSONB(), nullable=False),
        sa.Column("valid_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "mpa_boundaries",
        sa.Column("id", UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            Geometry("MULTIPOLYGON", srid=4326), name="geometry", nullable=False
        ),
        sa.Column(
            "source", sa.String(length=128), nullable=False, server_default=sa.text("''")
        ),
        sa.Column(
            "version", sa.String(length=64), nullable=False, server_default=sa.text("''")
        ),
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "observations",
        sa.Column("id", UUID(), nullable=False),
        sa.Column("variable", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column(
            "unit", sa.String(length=32), nullable=False, server_default=sa.text("''")
        ),
        sa.Column(Geometry("POINT", srid=4326), name="geometry", nullable=True),
        sa.Column("valid_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_id", UUID(), nullable=True),
        sa.Column(
            "quality_flag",
            ENUM("good", "suspect", "missing", name="quality_flag"),
            nullable=False,
            server_default=sa.text("'good'"),
        ),
        sa.Column(
            "confidence", sa.Float(), nullable=False, server_default=sa.text("1.0")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["source_id"], ["data_source_health.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "route_plans",
        sa.Column("id", UUID(), nullable=False),
        sa.Column("user_id", UUID(), nullable=True),
        sa.Column("waypoints", JSONB(), nullable=False),
        sa.Column("departure_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            ENUM("draft", "active", "completed", "archived", name="route_status"),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )

    from app.db.base import Base

    dsh_table = Base.metadata.tables["data_source_health"]
    op.bulk_insert(
        dsh_table,
        [
            {"id": str(uuid.uuid4()), "name": "incois", "priority": 1, "status": "unavailable"},
            {"id": str(uuid.uuid4()), "name": "mosdac", "priority": 2, "status": "unavailable"},
            {"id": str(uuid.uuid4()), "name": "imd", "priority": 3, "status": "unavailable"},
        ],
    )


def downgrade() -> None:
    op.drop_table("route_plans")
    op.drop_table("observations")
    op.drop_table("mpa_boundaries")
    op.drop_table("pfz_zones")
    op.drop_table("warnings")
    op.drop_table("evidence_items")
    op.drop_table("agent_runs")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("data_source_health")
    op.drop_table("users")

    sa.Enum(name="route_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="quality_flag").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="source_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="agent_run_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="warning_severity").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
