"""Initial schema, deliberately independent of mutable application models."""

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    sql = Path(__file__).with_suffix(".sql").read_text()
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade():
    for name in ("worker_heartbeat", "alert_outbox", "incidents", "check_executions", "monitors"):
        op.drop_table(name)
