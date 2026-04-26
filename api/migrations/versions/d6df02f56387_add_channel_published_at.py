"""add channel_published_at em discovery_results_channels

Revision ID: d6df02f56387
Revises: 56a880b51364
Create Date: 2026-04-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d6df02f56387"
down_revision: Union[str, None] = "56a880b51364"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Data real de criação do canal no YouTube (do snippet.publishedAt vindo
    # de channels.list). Vem grátis nas descobertas — sem custo de quota.
    # Usado pela tela de Sugestões para "canal com até N dias de criação".
    op.add_column(
        "discovery_results_channels",
        sa.Column("channel_published_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("discovery_results_channels", "channel_published_at")
