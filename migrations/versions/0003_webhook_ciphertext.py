"""Durable encrypted webhook secrets for hosts with ephemeral filesystems."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    # Nullable for existing local-vault channels; no secrets are read during migration.
    op.add_column(
        "notification_channels", sa.Column("webhook_ciphertext", sa.String(4096), nullable=True)
    )


def downgrade():
    op.drop_column("notification_channels", "webhook_ciphertext")
