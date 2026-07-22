"""add channel spike alert columns

Revision ID: f4a6b8c0d2e4
Revises: c9d1e3f5a7b2
Create Date: 2026-07-22 12:10:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f4a6b8c0d2e4"
down_revision = "c9d1e3f5a7b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alerta de pico de views por canal: ganho de views nas últimas 24h
    # comparado à média diária dos 7 dias anteriores, gatilho por multiplicador
    # (ex.: 2.0 = "2x acima do normal"). Desligado por padrão.
    op.add_column(
        "channels",
        sa.Column("spike_alert_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "channels",
        sa.Column("spike_alert_multiplier", sa.Float(), nullable=False, server_default=sa.text("2.0")),
    )
    # Cooldown: última vez que este canal disparou alerta (evita spam a cada sync).
    op.add_column(
        "channels",
        sa.Column("spike_last_alert_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("channels", "spike_last_alert_at")
    op.drop_column("channels", "spike_alert_multiplier")
    op.drop_column("channels", "spike_alert_enabled")
