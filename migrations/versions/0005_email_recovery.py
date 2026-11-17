"""Verified account emails, one-use actions and encrypted Gmail delivery queue."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("email", sa.String(254), nullable=True))
    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.add_column("users", sa.Column("pending_email", sa.String(254), nullable=True))
    op.create_index("ix_users_pending_email", "users", ["pending_email"])
    op.add_column(
        "users",
        sa.Column("requires_verification", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "email_actions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("purpose", sa.String(10), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_email_actions_user_id", "email_actions", ["user_id"])
    op.create_index("ix_email_actions_expires_at", "email_actions", ["expires_at"])
    op.create_table(
        "mail_deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "action_hash",
            sa.String(64),
            sa.ForeignKey("email_actions.token_hash", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("ciphertext", sa.String(8192), nullable=True),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.String(40), nullable=True),
    )


def downgrade():
    op.drop_table("mail_deliveries")
    op.drop_table("email_actions")
    op.drop_column("users", "requires_verification")
    op.drop_index("ix_users_pending_email", "users")
    op.drop_column("users", "pending_email")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_column("users", "email")
