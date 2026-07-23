"""add channel is_favorite

Revision ID: a8c0d2e4f6b8
Revises: f4a6b8c0d2e4
Create Date: 2026-07-22 21:30:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a8c0d2e4f6b8"
down_revision = "f4a6b8c0d2e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Favorito do usuário (estrela no Monitoramento). A observação/nota livre
    # reusa a coluna `notes` que já existe.
    op.add_column(
        "channels",
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("channels", "is_favorite")
