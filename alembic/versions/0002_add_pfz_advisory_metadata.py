"""add_pfz_advisory_metadata

Revision ID: 0002_add_pfz_advisory_metadata
Revises: 0001_initial
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_add_pfz_advisory_metadata"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("pfz_zones", "score", existing_type=sa.Float(), nullable=True)

    op.add_column(
        "pfz_zones",
        sa.Column("source_type", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "pfz_zones",
        sa.Column("source_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "pfz_zones",
        sa.Column("sector", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "pfz_zones",
        sa.Column("landing_center", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "pfz_zones",
        sa.Column("depth", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "pfz_zones",
        sa.Column("distance_km", sa.Float(), nullable=True),
    )
    op.add_column(
        "pfz_zones",
        sa.Column("direction", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "pfz_zones",
        sa.Column("forecast_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "pfz_zones",
        sa.Column("valid_until", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pfz_zones", "valid_until")
    op.drop_column("pfz_zones", "forecast_date")
    op.drop_column("pfz_zones", "direction")
    op.drop_column("pfz_zones", "distance_km")
    op.drop_column("pfz_zones", "depth")
    op.drop_column("pfz_zones", "landing_center")
    op.drop_column("pfz_zones", "sector")
    op.drop_column("pfz_zones", "source_name")
    op.drop_column("pfz_zones", "source_type")

    op.alter_column(
        "pfz_zones",
        "score",
        existing_type=sa.Float(),
        nullable=False,
    )
