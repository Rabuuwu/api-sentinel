"""Dashboard metrics, degradation, events, channels and safe public pages."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    statements = [
        "ALTER TABLE monitors ADD COLUMN description VARCHAR(1000) NOT NULL DEFAULT ''",
        "ALTER TABLE monitors ADD COLUMN degraded_latency_ms INTEGER",
        "ALTER TABLE monitors ADD COLUMN degraded_threshold INTEGER NOT NULL DEFAULT 3",
        "ALTER TABLE monitors ADD COLUMN consecutive_degraded INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE monitors ADD COLUMN notification_channel_ids UUID[] NOT NULL DEFAULT '{}'",
        "ALTER TABLE monitors DROP CONSTRAINT monitors_status_check",
        "ALTER TABLE monitors ADD CONSTRAINT ck_monitor_status CHECK "
        "(status IN ('UNKNOWN','UP','DEGRADED','DOWN','PAUSED'))",
        "ALTER TABLE monitors ADD CONSTRAINT ck_degraded_latency CHECK "
        "(degraded_latency_ms IS NULL OR degraded_latency_ms BETWEEN 1 AND 30000)",
        "ALTER TABLE monitors ADD CONSTRAINT ck_degraded_threshold CHECK "
        "(degraded_threshold BETWEEN 1 AND 100)",
        "ALTER TABLE incidents ADD COLUMN failed_checks INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE incidents ADD COLUMN recovery_successes INTEGER NOT NULL DEFAULT 0",
        "UPDATE incidents SET failed_checks = failure_count_at_open",
        "UPDATE incidents i SET failed_checks = GREATEST(i.failure_count_at_open, "
        "(SELECT count(*) FROM check_executions e WHERE e.monitor_id=i.monitor_id "
        "AND e.started_at >= i.started_at AND e.finished_at <= COALESCE(i.resolved_at, now()) "
        "AND e.result NOT IN ('SUCCESS','DEGRADED','ABORTED')))",
        "ALTER TABLE alert_outbox ALTER COLUMN incident_id DROP NOT NULL",
        "ALTER TABLE alert_outbox ALTER COLUMN channel TYPE VARCHAR(80)",
        "CREATE TABLE notification_channels (id UUID PRIMARY KEY, name VARCHAR(120) NOT NULL, "
        "provider VARCHAR(20) NOT NULL, enabled BOOLEAN NOT NULL, on_down BOOLEAN NOT NULL, "
        "on_recovered BOOLEAN NOT NULL, deleted_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL)",
        "CREATE TABLE monitor_events (id UUID PRIMARY KEY, monitor_id UUID NOT NULL "
        "REFERENCES monitors(id), action VARCHAR(40) NOT NULL, information JSONB NOT NULL, "
        "created_at TIMESTAMPTZ NOT NULL)",
        "CREATE INDEX ix_events_history ON monitor_events(monitor_id, created_at, id)",
        # Use the original monitor timestamp; do not invent historical failures or notifications.
        "INSERT INTO monitor_events SELECT id, id, 'MONITOR_CREATED', '{}'::jsonb, created_at "
        "FROM monitors",
        "CREATE TABLE status_pages (id UUID PRIMARY KEY, name VARCHAR(120) NOT NULL, "
        "slug VARCHAR(80) NOT NULL UNIQUE, description VARCHAR(1000) NOT NULL, "
        "published BOOLEAN NOT NULL, monitor_ids UUID[] NOT NULL, created_at TIMESTAMPTZ NOT NULL)",
    ]
    for sql in statements:
        op.execute(sql)


def downgrade():
    for table in ("status_pages", "monitor_events", "notification_channels"):
        op.drop_table(table)
    op.execute("DELETE FROM alert_outbox WHERE incident_id IS NULL")
    op.execute("ALTER TABLE alert_outbox ALTER COLUMN incident_id SET NOT NULL")
    # Leave VARCHAR(80): shrinking would truncate channel IDs in historical deliveries.
    op.execute("ALTER TABLE monitors DROP CONSTRAINT ck_monitor_status")
    op.execute("UPDATE monitors SET status='UP' WHERE status='DEGRADED'")
    op.execute(
        "ALTER TABLE monitors ADD CONSTRAINT monitors_status_check "
        "CHECK(status IN ('UNKNOWN','UP','DOWN','PAUSED'))"
    )
    op.execute("ALTER TABLE monitors DROP CONSTRAINT ck_degraded_latency")
    op.execute("ALTER TABLE monitors DROP CONSTRAINT ck_degraded_threshold")
    for column in (
        "description",
        "degraded_latency_ms",
        "degraded_threshold",
        "consecutive_degraded",
        "notification_channel_ids",
    ):
        op.drop_column("monitors", column)
    op.drop_column("incidents", "failed_checks")
    op.drop_column("incidents", "recovery_successes")
