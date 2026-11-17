"""Accounts and ownership. Legacy rows stay unclaimed until authenticated bootstrap."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("username", sa.String(40), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_table(
        "account_invitations",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_account_invitations_expires_at", "account_invitations", ["expires_at"])
    op.create_table(
        "auth_budgets",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_budgets_expires_at", "auth_budgets", ["expires_at"])
    for table in ("monitors", "notification_channels", "status_pages"):
        op.add_column(table, sa.Column("owner_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(f"fk_{table}_owner", table, "users", ["owner_id"], ["id"])
        op.create_index(f"ix_{table}_owner_id", table, ["owner_id"])


def downgrade():
    raise RuntimeError("Account migration is not automatically reversible; restore a backup")
