"""add discovery thumbnails and video unavailable fields

Revision ID: 1f7c9e4b2d11
Revises: d6df02f56387
Create Date: 2026-04-26 12:10:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "1f7c9e4b2d11"
down_revision = "d6df02f56387"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "discovery_results_channels",
        sa.Column("thumbnail_url", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "discovery_results_videos",
        sa.Column("thumbnail_url", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "tracked_videos",
        sa.Column("unavailable_reason", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "tracked_videos",
        sa.Column("unavailable_since", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tracked_videos", "unavailable_since")
    op.drop_column("tracked_videos", "unavailable_reason")
    op.drop_column("discovery_results_videos", "thumbnail_url")
    op.drop_column("discovery_results_channels", "thumbnail_url")
