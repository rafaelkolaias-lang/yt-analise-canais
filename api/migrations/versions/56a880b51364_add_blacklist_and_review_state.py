"""add channel_blacklist + reviewed_at em discovery_results

Revision ID: 56a880b51364
Revises: 59b9687df885
Create Date: 2026-04-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "56a880b51364"
down_revision: Union[str, None] = "59b9687df885"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "channel_blacklist",
        sa.Column(
            "id",
            sa.BigInteger(),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "youtube_channel_id",
            sa.String(length=32),
            nullable=False,
            unique=True,
        ),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column(
            "blacklisted_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_channel_blacklist_youtube_channel_id",
        "channel_blacklist",
        ["youtube_channel_id"],
    )

    op.add_column(
        "discovery_results_channels",
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "discovery_results_videos",
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("discovery_results_videos", "reviewed_at")
    op.drop_column("discovery_results_channels", "reviewed_at")
    op.drop_index(
        "ix_channel_blacklist_youtube_channel_id",
        table_name="channel_blacklist",
    )
    op.drop_table("channel_blacklist")
