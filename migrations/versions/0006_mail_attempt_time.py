"""Nullable delivery timestamp, no credentials or message content."""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("mail_deliveries", sa.Column("last_attempt_at", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_column("mail_deliveries", "last_attempt_at")
