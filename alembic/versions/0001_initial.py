"""initial schema: users, applications, events, job_offers, matches

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("skills", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("desired_position", sa.String(255), nullable=True),
        sa.Column(
            "seniority",
            sa.Enum("junior", "mid", "senior", name="seniority_enum"),
            nullable=True,
        ),
        sa.Column("min_salary", sa.Integer(), nullable=True),
        sa.Column(
            "preferred_language",
            sa.Enum("ca", "es", "en", name="preferred_language_enum"),
            nullable=False,
            server_default="es",
        ),
        sa.Column("last_match_search_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("position", sa.String(255), nullable=False),
        sa.Column(
            "status",
            sa.Enum("saved", "applied", "interview", "offer", "rejected", "withdrawn", name="application_status_enum"),
            nullable=False,
            server_default="saved",
        ),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("salary_range", sa.String(100), nullable=True),
        sa.Column("job_url", sa.String(1000), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_applications_user_id", "applications", ["user_id"])
    op.create_index("ix_applications_status", "applications", ["status"])

    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "type",
            sa.Enum("interview", "follow_up", "note", "status_change", name="event_type_enum"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("event_date", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_events_application_id", "events", ["application_id"])

    op.create_table(
        "job_offers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("salary_range", sa.String(100), nullable=True),
        sa.Column("url", sa.String(1000), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source", "external_id", name="uq_job_offers_source_external_id"),
    )
    op.create_index("ix_job_offers_external_id", "job_offers", ["external_id"])

    op.create_table(
        "matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "job_offer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("job_offers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("new", "dismissed", "converted", name="match_status_enum"),
            nullable=False,
            server_default="new",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "job_offer_id", name="uq_matches_user_job_offer"),
    )
    op.create_index("ix_matches_user_id", "matches", ["user_id"])
    op.create_index("ix_matches_job_offer_id", "matches", ["job_offer_id"])
    op.create_index("ix_matches_status", "matches", ["status"])


def downgrade() -> None:
    op.drop_table("matches")
    op.drop_table("job_offers")
    op.drop_table("events")
    op.drop_table("applications")
    op.drop_table("users")

    bind = op.get_bind()
    for enum_name in (
        "match_status_enum",
        "event_type_enum",
        "application_status_enum",
        "preferred_language_enum",
        "seniority_enum",
    ):
        sa.Enum(name=enum_name).drop(bind, checkfirst=True)
