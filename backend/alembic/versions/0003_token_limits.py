"""per-user token limits + usage tracking

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("daily_token_limit", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("tokens_used_today", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("tokens_used_total", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column("users", sa.Column("usage_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "usage_date")
    op.drop_column("users", "tokens_used_total")
    op.drop_column("users", "tokens_used_today")
    op.drop_column("users", "daily_token_limit")
