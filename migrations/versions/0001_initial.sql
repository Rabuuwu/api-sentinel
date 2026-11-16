CREATE TABLE monitors (
 id UUID PRIMARY KEY, name VARCHAR(120) NOT NULL, url VARCHAR(2048) NOT NULL,
 method VARCHAR(4) NOT NULL CHECK (method IN ('GET','HEAD')),
 interval_seconds INTEGER NOT NULL CHECK (interval_seconds BETWEEN 60 AND 86400),
 timeout_seconds INTEGER NOT NULL CHECK (timeout_seconds BETWEEN 2 AND 30),
 expected_status_min INTEGER NOT NULL CHECK (expected_status_min BETWEEN 100 AND 599),
 expected_status_max INTEGER NOT NULL CHECK (expected_status_max BETWEEN expected_status_min AND 599),
 failure_threshold INTEGER NOT NULL CHECK (failure_threshold BETWEEN 1 AND 100),
 recovery_threshold INTEGER NOT NULL CHECK (recovery_threshold BETWEEN 1 AND 100),
 mode VARCHAR(20) NOT NULL CHECK (mode = 'standard'),
 status VARCHAR(20) NOT NULL CHECK (status IN ('UNKNOWN','UP','DOWN','PAUSED')),
 consecutive_failures INTEGER NOT NULL, consecutive_successes INTEGER NOT NULL,
 generation INTEGER NOT NULL, failure_started_at TIMESTAMPTZ, last_checked_at TIMESTAMPTZ,
 next_run_at TIMESTAMPTZ NOT NULL, paused_at TIMESTAMPTZ, deleted_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_monitors_due ON monitors(next_run_at) WHERE paused_at IS NULL AND deleted_at IS NULL;
CREATE INDEX ix_monitors_status ON monitors(status);
CREATE TABLE check_executions (
 id UUID PRIMARY KEY, monitor_id UUID NOT NULL REFERENCES monitors(id), generation INTEGER NOT NULL,
 scheduled_for TIMESTAMPTZ NOT NULL, started_at TIMESTAMPTZ NOT NULL, finished_at TIMESTAMPTZ,
 result VARCHAR(30), http_status INTEGER, latency_ms DOUBLE PRECISION, created_at TIMESTAMPTZ NOT NULL,
 UNIQUE(monitor_id, scheduled_for)
);
CREATE INDEX ix_checks_history ON check_executions(monitor_id, finished_at, id);
CREATE TABLE incidents (
 id UUID PRIMARY KEY, monitor_id UUID NOT NULL REFERENCES monitors(id),
 state VARCHAR(20) NOT NULL CHECK (state IN ('OPEN','RESOLVED')),
 started_at TIMESTAMPTZ NOT NULL, detected_at TIMESTAMPTZ NOT NULL, resolved_at TIMESTAMPTZ,
 failure_count_at_open INTEGER NOT NULL, reason VARCHAR(50) NOT NULL, created_at TIMESTAMPTZ NOT NULL
);
CREATE UNIQUE INDEX ix_one_open_incident ON incidents(monitor_id) WHERE state = 'OPEN';
CREATE INDEX ix_incidents_history ON incidents(monitor_id, created_at, id);
CREATE TABLE alert_outbox (
 id UUID PRIMARY KEY, incident_id UUID NOT NULL REFERENCES incidents(id),
 event_type VARCHAR(30) NOT NULL, channel VARCHAR(20) NOT NULL,
 delivery_state VARCHAR(20) NOT NULL, attempts INTEGER NOT NULL,
 next_attempt_at TIMESTAMPTZ NOT NULL, last_error_sanitized VARCHAR(80), sent_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL, UNIQUE(incident_id, event_type, channel)
);
CREATE INDEX ix_alert_outbox_incident_id ON alert_outbox(incident_id);
CREATE INDEX ix_alerts_due ON alert_outbox(delivery_state, next_attempt_at);
CREATE TABLE worker_heartbeat (id INTEGER PRIMARY KEY, updated_at TIMESTAMPTZ NOT NULL);
