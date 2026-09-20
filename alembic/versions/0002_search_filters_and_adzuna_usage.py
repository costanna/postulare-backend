"""filtros de busqueda por usuario y contador diario de llamadas a Adzuna

Revision ID: 0002_search_filters_usage
Revises: 0001_initial
Create Date: 2026-09-20

Solo aditiva: una columna nullable y una tabla nueva. No toca datos existentes.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_search_filters_usage"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("search_filters", sa.JSON(), nullable=True))
    op.create_table(
        "adzuna_usage",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("calls", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("adzuna_usage")
    op.drop_column("users", "search_filters")
