"""add notifications table

Revision ID: a1c5e9d8b3f0
Revises: 1f7c9e4b2d11
Create Date: 2026-04-26 18:00:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1c5e9d8b3f0"
down_revision = "1f7c9e4b2d11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        # Origem/categoria. Strings livres para permitir novos tipos sem migration.
        # Tipos atuais: "task_progress", "task_done", "task_error", "system_alert",
        # "suggestions_changed".
        sa.Column("type", sa.String(length=64), nullable=False),
        # Estado atual. "running" | "success" | "error" | "info".
        sa.Column("status", sa.String(length=32), nullable=False),
        # Texto curto (cabeçalho do card).
        sa.Column("title", sa.String(length=255), nullable=False),
        # Texto longo opcional (corpo do card).
        sa.Column("message", sa.Text(), nullable=True),
        # 0–100, usado quando status="running".
        sa.Column("progress_pct", sa.Integer(), nullable=True),
        # JSON livre para extras (ex: {"sync_run_id": 123, "channel_ids": [...]}).
        sa.Column("metadata_json", sa.Text(), nullable=True),
        # Permite agrupar/atualizar uma notificação ao longo do tempo (ex: o sync
        # manual atualiza a mesma notification durante a execução).
        sa.Column("source_key", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            server_onupdate=sa.func.now(),
        ),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_notifications_dismissed_created",
        "notifications",
        ["dismissed_at", "created_at"],
    )
    op.create_index(
        "ix_notifications_source_key",
        "notifications",
        ["source_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_source_key", table_name="notifications")
    op.drop_index("ix_notifications_dismissed_created", table_name="notifications")
    op.drop_table("notifications")
