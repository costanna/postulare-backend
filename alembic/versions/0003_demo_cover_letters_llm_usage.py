"""cuentas demo, resumen profesional, cartas de presentacion y contador de uso de la IA

Revision ID: 0003_demo_letters_llm
Revises: 0002_search_filters_usage
Create Date: 2026-09-21

Solo aditiva: columnas nuevas (nullable o con valor por defecto) y una tabla
nueva. No toca datos existentes.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_demo_letters_llm"
down_revision: Union[str, None] = "0002_search_filters_usage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("about", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("matches", sa.Column("cover_letter", sa.Text(), nullable=True))
    op.add_column("matches", sa.Column("cover_letter_source", sa.String(16), nullable=True))
    op.add_column("matches", sa.Column("cover_letter_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "llm_usage",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("scope", sa.String(64), primary_key=True),
        sa.Column("calls", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("llm_usage")
    op.drop_column("matches", "cover_letter_at")
    op.drop_column("matches", "cover_letter_source")
    op.drop_column("matches", "cover_letter")
    op.drop_column("users", "is_demo")
    op.drop_column("users", "about")
