"""idioma de la carta de presentacion guardada

Revision ID: 0004_cover_letter_lang
Revises: 0003_demo_letters_llm
Create Date: 2026-09-22

Solo aditiva: una columna nullable.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_cover_letter_lang"
down_revision: Union[str, None] = "0003_demo_letters_llm"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("cover_letter_language", sa.String(2), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "cover_letter_language")
