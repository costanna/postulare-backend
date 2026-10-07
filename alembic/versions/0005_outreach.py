"""cvs por idioma, directorio de espontaneas y registro de envios

Revision ID: 0005_outreach
Revises: 0004_cover_letter_lang
Create Date: 2026-10-07

Solo aditiva: tres tablas nuevas.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_outreach"
down_revision: Union[str, None] = "0004_cover_letter_lang"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_cvs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "language", name="uq_user_cvs_user_language"),
    )
    op.create_index("ix_user_cvs_user_id", "user_cvs", ["user_id"])

    op.create_table(
        "target_companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("language", sa.String(2), nullable=False, server_default="es"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "email", name="uq_targets_user_email"),
    )
    op.create_index("ix_target_companies_user_id", "target_companies", ["user_id"])

    op.create_table(
        "email_sends",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("matches.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "target_company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("target_companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("company_key", sa.String(255), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="offer"),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_email_sends_user_id", "email_sends", ["user_id"])
    op.create_index("ix_email_sends_company_key", "email_sends", ["company_key"])


def downgrade() -> None:
    op.drop_table("email_sends")
    op.drop_table("target_companies")
    op.drop_table("user_cvs")
