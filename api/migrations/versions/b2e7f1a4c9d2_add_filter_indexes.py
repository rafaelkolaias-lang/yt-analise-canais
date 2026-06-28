"""add filter indexes (channels.status/is_active, tracked_videos.status)

Revision ID: b2e7f1a4c9d2
Revises: a1c5e9d8b3f0
Create Date: 2026-06-27 22:30:00

Índices em colunas usadas como filtro quente:
  - channels.status      → analytics/monitoramento filtram por status
  - channels.is_active   → sync varre canais ativos
  - tracked_videos.status→ analytics conta vídeos active; sync filtra por status

Apenas CREATE INDEX (não destrutivo, seguro de aplicar em prod).
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "b2e7f1a4c9d2"
down_revision = "a1c5e9d8b3f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_channels_status", "channels", ["status"])
    op.create_index("ix_channels_is_active", "channels", ["is_active"])
    op.create_index("ix_tracked_videos_status", "tracked_videos", ["status"])


def downgrade() -> None:
    op.drop_index("ix_tracked_videos_status", table_name="tracked_videos")
    op.drop_index("ix_channels_is_active", table_name="channels")
    op.drop_index("ix_channels_status", table_name="channels")
