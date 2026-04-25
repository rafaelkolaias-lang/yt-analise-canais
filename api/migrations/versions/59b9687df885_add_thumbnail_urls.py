"""add thumbnail urls to channels and tracked_videos

Revision ID: 59b9687df885
Revises: d69d8c5c7a0e
Create Date: 2026-04-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "59b9687df885"
down_revision: Union[str, None] = "d69d8c5c7a0e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "channels",
        sa.Column("thumbnail_url", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "tracked_videos",
        sa.Column("thumbnail_url", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tracked_videos", "thumbnail_url")
    op.drop_column("channels", "thumbnail_url")
