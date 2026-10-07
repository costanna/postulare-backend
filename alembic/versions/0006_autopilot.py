"""pausa del piloto y tags de matching en espontaneas

Revision ID: 0006_autopilot
Revises: 0005_outreach
Create Date: 2026-10-07

Solo aditiva: una columna en users y una en target_companies.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_autopilot"
down_revision: Union[str, None] = "0005_outreach"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("auto_outreach_paused", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("target_companies", sa.Column("tags", sa.JSON(), server_default="[]", nullable=False))


def downgrade() -> None:
    op.drop_column("target_companies", "tags")
    op.drop_column("users", "auto_outreach_paused")
