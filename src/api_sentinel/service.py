from datetime import timedelta
from uuid import UUID

from sqlalchemy import delete, select, update

from api_sentinel.checker import CheckResult
from api_sentinel.db import Database
from api_sentinel.domain import transition
from api_sentinel.models import (
    Alert,
    Execution,
    Incident,
    Monitor,
    MonitorEvent,
    NotificationChannel,
    WorkerHeartbeat,
    now,
)
from api_sentinel.schemas import MonitorInput


def monitor_input(monitor: Monitor) -> MonitorInput:
    return MonitorInput.model_validate({k: getattr(monitor, k) for k in MonitorInput.model_fields})


async def reserve(db: Database, limit: int) -> list[tuple[UUID, MonitorInput]]:
    work = []
    async with db.sessions.begin() as session:
        monitors = (
            await session.scalars(
                select(Monitor)
                .where(
                    Monitor.deleted_at.is_(None),
                    Monitor.paused_at.is_(None),
                    Monitor.next_run_at <= now(),
                )
                .order_by(Monitor.next_run_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for monitor in monitors:
            execution = Execution(
                monitor_id=monitor.id,
                generation=monitor.generation,
                scheduled_for=monitor.next_run_at,
            )
            session.add(execution)
            monitor.next_run_at = now() + timedelta(seconds=monitor.interval_seconds)
            await session.flush()
            work.append((execution.id, monitor_input(monitor)))
    return work


async def record(db: Database, execution_id: UUID, result: CheckResult, channel: str):
    async with db.sessions.begin() as session:
        execution = await session.scalar(
            select(Execution).where(Execution.id == execution_id).with_for_update()
        )
        if execution is None or execution.finished_at is not None:
            return  # Idempotent result processing, including concurrent submissions.
        execution.finished_at = now()
        execution.result = result.result
        execution.http_status = result.http_status
        execution.latency_ms = result.latency_ms
        monitor = await session.scalar(
            select(Monitor).where(Monitor.id == execution.monitor_id).with_for_update()
        )
        if (
            monitor is None
            or monitor.deleted_at
            or monitor.paused_at
            or monitor.generation != execution.generation
        ):
            return  # Retain history, but stale checks cannot change current monitor state.
        monitor.last_checked_at = execution.finished_at
        success = result.result in ("SUCCESS", "DEGRADED")
        slow = bool(
            success
            and monitor.degraded_latency_ms is not None
            and result.latency_ms is not None
            and result.latency_ms >= monitor.degraded_latency_ms
        )
        if slow:
            execution.result = "DEGRADED"
        if not success:
            session.add(
                MonitorEvent(
                    monitor_id=monitor.id,
                    action="MONITOR_FAILED",
                    information={
                        "status": result.http_status,
                        "reason": result.result,
                        "latency_ms": result.latency_ms,
                    },
                )
            )
        if not success and monitor.consecutive_failures == 0:
            monitor.failure_started_at = execution.started_at
        state = transition(
            monitor.status,
            monitor.consecutive_failures,
            monitor.consecutive_successes,
            success,
            monitor.failure_threshold,
            monitor.recovery_threshold,
            slow,
            monitor.consecutive_degraded,
            monitor.degraded_threshold,
        )
        monitor.status = state.status
        monitor.consecutive_failures = state.failures
        monitor.consecutive_successes = state.successes
        monitor.consecutive_degraded = state.degraded
        existing = await session.scalar(
            select(Incident).where(Incident.monitor_id == monitor.id, Incident.state == "OPEN")
        )
        if existing:
            existing.failed_checks += int(not success)
            existing.recovery_successes = state.successes
        if state.event == "INCIDENT_OPENED":
            incident = Incident(
                monitor_id=monitor.id,
                started_at=monitor.failure_started_at or execution.started_at,
                failure_count_at_open=state.failures,
                reason=result.result,
                failed_checks=state.failures,
            )
            session.add(incident)
            await session.flush()
            await enqueue_alerts(session, monitor, incident, state.event, channel)
            session.add(
                MonitorEvent(
                    monitor_id=monitor.id,
                    action="INCIDENT_CREATED",
                    information={"incident_id": str(incident.id)},
                )
            )
        elif state.event == "INCIDENT_RESOLVED":
            resolved_incident = await session.scalar(
                select(Incident).where(Incident.monitor_id == monitor.id, Incident.state == "OPEN")
            )
            if resolved_incident:
                incident = resolved_incident
                incident.state = "RESOLVED"
                incident.resolved_at = execution.finished_at
                incident.recovery_successes = state.successes
                await enqueue_alerts(session, monitor, incident, state.event, channel)
                session.add(
                    MonitorEvent(
                        monitor_id=monitor.id,
                        action="MONITOR_RECOVERED",
                        information={
                            "incident_id": str(incident.id),
                            "latency_ms": result.latency_ms,
                        },
                    )
                )
        elif state.event:
            session.add(
                MonitorEvent(
                    monitor_id=monitor.id,
                    action=state.event,
                    information={"latency_ms": result.latency_ms},
                )
            )
        if success:
            monitor.failure_started_at = None


async def recover_abandoned(db: Database):
    """Only called after obtaining the singleton worker lock, never during active checks."""
    async with db.sessions.begin() as session:
        ids = list(
            (
                await session.scalars(
                    select(Execution.monitor_id).where(Execution.finished_at.is_(None))
                )
            ).all()
        )
        await session.execute(
            update(Execution)
            .where(Execution.finished_at.is_(None))
            .values(result="ABORTED", finished_at=now())
        )
        if ids:
            await session.execute(
                update(Monitor)
                .where(Monitor.id.in_(ids))
                .values(
                    consecutive_failures=0,
                    consecutive_successes=0,
                    consecutive_degraded=0,
                    failure_started_at=None,
                )
            )


async def housekeeping(db: Database, retention_days: int):
    async with db.sessions.begin() as session:
        heartbeat = await session.get(WorkerHeartbeat, 1)
        if heartbeat:
            heartbeat.updated_at = now()
        else:
            session.add(WorkerHeartbeat(id=1))
        await session.execute(
            delete(Execution).where(Execution.finished_at < now() - timedelta(days=retention_days))
        )
        await session.execute(
            delete(MonitorEvent).where(
                MonitorEvent.action.in_(["MONITOR_FAILED", "MONITOR_DEGRADED"]),
                MonitorEvent.created_at < now() - timedelta(days=retention_days),
            )
        )


async def enqueue_alerts(session, monitor, incident, event, fallback):
    channels = (
        list(
            (
                await session.scalars(
                    select(NotificationChannel).where(
                        NotificationChannel.id.in_(monitor.notification_channel_ids),
                        NotificationChannel.owner_id == monitor.owner_id,
                        NotificationChannel.deleted_at.is_(None),
                        NotificationChannel.enabled.is_(True),
                    )
                )
            ).all()
        )
        if monitor.notification_channel_ids
        else []
    )
    targets = [
        f"discord:{item.id}"
        for item in channels
        if (item.on_down if event == "INCIDENT_OPENED" else item.on_recovered)
    ]
    if not monitor.notification_channel_ids:
        targets = ["console" if monitor.owner_id else fallback]
    for target in targets:
        session.add(Alert(incident_id=incident.id, event_type=event, channel=target))
