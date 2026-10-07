"""pdf original guardado en cvs por idioma

Revision ID: 0007_cv_pdf
Revises: 0006_autopilot
Create Date: 2026-10-07

Solo aditiva: dos columnas nullables en user_cvs.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_cv_pdf"
down_revision: Union[str, None] = "0006_autopilot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_cvs", sa.Column("file_data", sa.LargeBinary(), nullable=True))
    op.add_column("user_cvs", sa.Column("filename", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("user_cvs", "filename")
    op.drop_column("user_cvs", "file_data")
