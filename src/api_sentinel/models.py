import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Monitor(Base):
    __tablename__ = "monitors"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(1000), default="", server_default="")
    degraded_latency_ms: Mapped[int | None]
    degraded_threshold: Mapped[int] = mapped_column(default=3, server_default="3")
    consecutive_degraded: Mapped[int] = mapped_column(default=0, server_default="0")
    notification_channel_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), default=list, server_default="{}"
    )
    url: Mapped[str] = mapped_column(String(2048))
    method: Mapped[str] = mapped_column(String(4), default="GET")
    interval_seconds: Mapped[int] = mapped_column(default=300)
    timeout_seconds: Mapped[int] = mapped_column(default=20)
    expected_status_min: Mapped[int] = mapped_column(default=200)
    expected_status_max: Mapped[int] = mapped_column(default=299)
    failure_threshold: Mapped[int] = mapped_column(default=3)
    recovery_threshold: Mapped[int] = mapped_column(default=2)
    mode: Mapped[str] = mapped_column(String(20), default="standard")
    status: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    consecutive_failures: Mapped[int] = mapped_column(default=0)
    consecutive_successes: Mapped[int] = mapped_column(default=0)
    generation: Mapped[int] = mapped_column(default=0)
    failure_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    __table_args__ = (
        CheckConstraint("interval_seconds BETWEEN 60 AND 86400"),
        CheckConstraint("timeout_seconds BETWEEN 2 AND 30"),
        CheckConstraint("failure_threshold BETWEEN 1 AND 100"),
        CheckConstraint("recovery_threshold BETWEEN 1 AND 100"),
        CheckConstraint("expected_status_min BETWEEN 100 AND 599"),
        CheckConstraint("expected_status_max BETWEEN expected_status_min AND 599"),
        CheckConstraint("method IN ('GET','HEAD')"),
        CheckConstraint(
            "status IN ('UNKNOWN','UP','DEGRADED','DOWN','PAUSED')", name="ck_monitor_status"
        ),
        CheckConstraint(
            "degraded_latency_ms IS NULL OR degraded_latency_ms BETWEEN 1 AND 30000",
            name="ck_degraded_latency",
        ),
        CheckConstraint("degraded_threshold BETWEEN 1 AND 100", name="ck_degraded_threshold"),
        CheckConstraint("mode = 'standard'"),
        Index(
            "ix_monitors_due",
            "next_run_at",
            postgresql_where=paused_at.is_(None) & deleted_at.is_(None),
        ),
        Index("ix_monitors_status", "status"),
    )


class Execution(Base):
    __tablename__ = "check_executions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    monitor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("monitors.id"))
    generation: Mapped[int]
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[str | None] = mapped_column(String(30))
    http_status: Mapped[int | None]
    latency_ms: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        UniqueConstraint("monitor_id", "scheduled_for"),
        Index("ix_checks_history", "monitor_id", "finished_at", "id"),
    )


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    monitor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("monitors.id"))
    state: Mapped[str] = mapped_column(String(20), default="OPEN")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_count_at_open: Mapped[int]
    failed_checks: Mapped[int] = mapped_column(default=0, server_default="0")
    recovery_successes: Mapped[int] = mapped_column(default=0, server_default="0")
    reason: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        CheckConstraint("state IN ('OPEN','RESOLVED')"),
        Index("ix_one_open_incident", "monitor_id", unique=True, postgresql_where=state == "OPEN"),
        Index("ix_incidents_history", "monitor_id", "created_at", "id"),
    )


class Alert(Base):
    __tablename__ = "alert_outbox"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("incidents.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(30))
    channel: Mapped[str] = mapped_column(String(80))
    delivery_state: Mapped[str] = mapped_column(String(20), default="PENDING")
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_error_sanitized: Mapped[str | None] = mapped_column(String(80))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        UniqueConstraint("incident_id", "event_type", "channel"),
        Index("ix_alerts_due", "delivery_state", "next_attempt_at"),
    )


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeat"
    id: Mapped[int] = mapped_column(primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class NotificationChannel(Base):
    __tablename__ = "notification_channels"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(String(20), default="discord")
    webhook_ciphertext: Mapped[str | None] = mapped_column(String(4096))
    enabled: Mapped[bool] = mapped_column(default=True)
    on_down: Mapped[bool] = mapped_column(default=True)
    on_recovered: Mapped[bool] = mapped_column(default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MonitorEvent(Base):
    __tablename__ = "monitor_events"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    monitor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("monitors.id"))
    action: Mapped[str] = mapped_column(String(40))
    information: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (Index("ix_events_history", "monitor_id", "created_at", "id"),)


class StatusPage(Base):
    __tablename__ = "status_pages"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str] = mapped_column(String(1000), default="")
    published: Mapped[bool] = mapped_column(default=False)
    monitor_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
