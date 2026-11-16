from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException, Query
from sqlalchemy import ColumnElement, func, select

from api_sentinel.dashboard_schemas import (
    ChannelInput,
    ChannelOut,
    ChannelPatch,
    MetricsOut,
    PublicPage,
    StatusPageInput,
)
from api_sentinel.metrics import SUCCESS, WINDOW_DAYS, Window, metrics, rate, summary
from api_sentinel.models import (
    Alert,
    Execution,
    Incident,
    Monitor,
    MonitorEvent,
    NotificationChannel,
    StatusPage,
    now,
)
from api_sentinel.vault import SecretVault


async def validate_channels(session, ids):
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "Duplicate notification channel")
    count = await session.scalar(
        select(func.count())
        .select_from(NotificationChannel)
        .where(NotificationChannel.id.in_(ids), NotificationChannel.deleted_at.is_(None))
    )
    if count != len(ids):
        raise HTTPException(422, "Notification channel not found")


def install_dashboard(app, router, Session, get_monitor, page, as_dict, settings):
    vault = SecretVault(settings.secrets_dir)

    @router.get("/monitors/{monitor_id}/metrics", response_model=MetricsOut)
    async def monitor_metrics(monitor_id: UUID, window: Window = "24h", session=Session):
        await get_monitor(session, monitor_id)
        return await metrics(session, monitor_id, window, now())

    @router.get("/monitors/{monitor_id}/timeline")
    async def timeline(
        monitor_id: UUID,
        limit: int = Query(20, ge=1, le=100),
        cursor: str | None = Query(None, max_length=256),
        session=Session,
    ):
        await get_monitor(session, monitor_id)
        return await page(
            session,
            select(MonitorEvent).where(MonitorEvent.monitor_id == monitor_id),
            MonitorEvent,
            "created_at",
            limit,
            cursor,
        )

    @router.get("/overview")
    async def overview(
        window: Window = "24h",
        q: str = Query("", max_length=120),
        status: str | None = Query(None, pattern="^(UP|DOWN|DEGRADED|UNKNOWN|PAUSED)$"),
        sort: str = Query("name", pattern="^(name|status|latency|uptime|last_check)$"),
        direction: str = Query("asc", pattern="^(asc|desc)$"),
        offset: int = Query(0, ge=0),
        limit: int = Query(25, ge=1, le=100),
        session=Session,
    ):
        end = now()
        start = end - timedelta(days=WINDOW_DAYS[window])
        aggregate = (
            select(
                Execution.monitor_id.label("mid"),
                func.count().label("total"),
                func.count().filter(Execution.result.in_(SUCCESS)).label("successful"),
                func.avg(Execution.latency_ms)
                .filter(Execution.result.in_(SUCCESS))
                .label("latency"),
            )
            .where(
                Execution.finished_at >= start,
                Execution.finished_at < end,
                Execution.result != "ABORTED",
            )
            .group_by(Execution.monitor_id)
            .subquery()
        )
        active = (
            select(Incident.monitor_id.label("mid"), Incident.id.label("incident_id"))
            .where(Incident.state == "OPEN")
            .subquery()
        )
        filters: list[ColumnElement[bool]] = [Monitor.deleted_at.is_(None)]
        if q:
            filters.append(Monitor.name.icontains(q, autoescape=True))
        if status:
            filters.append(Monitor.status == status)
        total = await session.scalar(select(func.count()).select_from(Monitor).where(*filters))
        uptime = aggregate.c.successful * 100.0 / func.nullif(aggregate.c.total, 0)
        columns = {
            "name": Monitor.name,
            "status": Monitor.status,
            "latency": aggregate.c.latency,
            "uptime": uptime,
            "last_check": Monitor.last_checked_at,
        }
        order = columns[sort].desc() if direction == "desc" else columns[sort].asc()
        rows = (
            await session.execute(
                select(
                    Monitor,
                    aggregate.c.total,
                    aggregate.c.successful,
                    aggregate.c.latency,
                    active.c.incident_id,
                )
                .outerjoin(aggregate, aggregate.c.mid == Monitor.id)
                .outerjoin(active, active.c.mid == Monitor.id)
                .where(*filters)
                .order_by(order.nulls_last(), Monitor.id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
        counts = dict(
            (
                await session.execute(
                    select(Monitor.status, func.count())
                    .where(Monitor.deleted_at.is_(None))
                    .group_by(Monitor.status)
                )
            ).all()
        )
        global_stats = await summary(session, start, end)
        open_count = await session.scalar(
            select(func.count())
            .select_from(Incident)
            .join(Monitor)
            .where(Incident.state == "OPEN", Monitor.deleted_at.is_(None))
        )
        return {
            "items": [
                {
                    **as_dict(m),
                    "uptime": rate(success or 0, count or 0),
                    "average_latency_ms": latency,
                    "active_incident_id": incident,
                }
                for m, count, success, latency, incident in rows
            ],
            "total": total,
            "offset": offset,
            "limit": limit,
            "summary": {
                "total": sum(counts.values()),
                "operational": counts.get("UP", 0),
                "degraded": counts.get("DEGRADED", 0),
                "down": counts.get("DOWN", 0),
                "unknown": counts.get("UNKNOWN", 0),
                "paused": counts.get("PAUSED", 0),
                "open_incidents": open_count,
                "average_ms": global_stats["average_ms"],
            },
        }

    @router.get("/incidents")
    async def incidents(
        state: str | None = Query(None, pattern="^(OPEN|RESOLVED)$"),
        limit: int = Query(25, ge=1, le=100),
        cursor: str | None = Query(None, max_length=256),
        session=Session,
    ):
        statement = select(Incident)
        if state:
            statement = statement.where(Incident.state == state)
        result = await page(session, statement, Incident, "created_at", limit, cursor)
        ids = [item["monitor_id"] for item in result["items"]]
        names = dict(
            (
                await session.execute(select(Monitor.id, Monitor.name).where(Monitor.id.in_(ids)))
            ).all()
        )
        for item in result["items"]:
            item["monitor_name"] = names.get(item["monitor_id"], "Deleted monitor")
            item["duration_seconds"] = (
                (item["resolved_at"] or now()) - item["started_at"]
            ).total_seconds()
        return result

    @router.get("/notifications", response_model=list[ChannelOut])
    async def channels(session=Session):
        return list(
            (
                await session.scalars(
                    select(NotificationChannel)
                    .where(NotificationChannel.deleted_at.is_(None))
                    .order_by(NotificationChannel.created_at)
                )
            ).all()
        )

    @router.post("/notifications", status_code=201, response_model=ChannelOut)
    async def create_channel(data: ChannelInput, session=Session):
        count = await session.scalar(
            select(func.count())
            .select_from(NotificationChannel)
            .where(NotificationChannel.deleted_at.is_(None))
        )
        if count >= 50:
            raise HTTPException(409, "Notification channel limit reached")
        channel = NotificationChannel(id=uuid4(), **data.model_dump(exclude={"webhook_url"}))
        session.add(channel)
        await session.flush()
        # Immutable secret per channel ID. Rollback may leave an unreferenced private file, never
        # change a live channel's credentials. Rotate by creating/reassigning a new channel.
        vault.write(channel.id, data.webhook_url.get_secret_value())
        return channel

    async def get_channel(session, key):
        channel = await session.scalar(
            select(NotificationChannel)
            .where(NotificationChannel.id == key, NotificationChannel.deleted_at.is_(None))
            .with_for_update()
        )
        if channel is None:
            raise HTTPException(404, "Notification channel not found")
        return channel

    @router.patch("/notifications/{channel_id}", response_model=ChannelOut)
    async def edit_channel(channel_id: UUID, data: ChannelPatch, session=Session):
        channel = await get_channel(session, channel_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            if value is None:
                raise HTTPException(422, "Null fields are not allowed")
            setattr(channel, key, value)
        return channel

    @router.delete("/notifications/{channel_id}", status_code=204)
    async def remove_channel(channel_id: UUID, session=Session):
        channel = await get_channel(session, channel_id)
        channel.deleted_at = now()
        channel.enabled = False

    @router.post("/notifications/{channel_id}/test", status_code=202)
    async def test_channel(channel_id: UUID, session=Session):
        channel = await get_channel(session, channel_id)
        if not channel.enabled:
            raise HTTPException(409, "Enable this channel before testing")
        target = f"discord:{channel.id}"
        recent = await session.scalar(
            select(Alert.id)
            .where(
                Alert.channel == target,
                Alert.event_type == "TEST",
                Alert.created_at > now() - timedelta(minutes=1),
            )
            .limit(1)
        )
        if recent:
            raise HTTPException(429, "Wait one minute before another test")
        alert = Alert(channel=target, event_type="TEST", incident_id=None)
        session.add(alert)
        await session.flush()
        return {"id": alert.id, "delivery_state": "PENDING"}

    @router.get("/notifications/{channel_id}/deliveries")
    async def deliveries(channel_id: UUID, session=Session):
        await get_channel(session, channel_id)
        rows = (
            await session.scalars(
                select(Alert)
                .where(Alert.channel == f"discord:{channel_id}")
                .order_by(Alert.created_at.desc())
                .limit(20)
            )
        ).all()
        return [as_dict(item) for item in rows]

    async def validate_page(session, data, existing_id=None):
        if len(set(data.monitor_ids)) != len(data.monitor_ids):
            raise HTTPException(422, "Duplicate monitor")
        count = await session.scalar(
            select(func.count())
            .select_from(Monitor)
            .where(Monitor.id.in_(data.monitor_ids), Monitor.deleted_at.is_(None))
        )
        if count != len(data.monitor_ids):
            raise HTTPException(422, "Monitor not found")
        duplicate = await session.scalar(select(StatusPage.id).where(StatusPage.slug == data.slug))
        if duplicate and duplicate != existing_id:
            raise HTTPException(409, "This status page slug is already used")

    @router.get("/status-pages")
    async def pages(session=Session):
        return [
            as_dict(item)
            for item in (
                await session.scalars(select(StatusPage).order_by(StatusPage.created_at))
            ).all()
        ]

    @router.post("/status-pages", status_code=201)
    async def create_page(data: StatusPageInput, session=Session):
        await validate_page(session, data)
        item = StatusPage(**data.model_dump())
        session.add(item)
        await session.flush()
        return as_dict(item)

    @router.put("/status-pages/{page_id}")
    async def edit_page(page_id: UUID, data: StatusPageInput, session=Session):
        item = await session.get(StatusPage, page_id)
        if item is None:
            raise HTTPException(404, "Status page not found")
        await validate_page(session, data, page_id)
        for key, value in data.model_dump().items():
            setattr(item, key, value)
        return as_dict(item)

    @router.delete("/status-pages/{page_id}", status_code=204)
    async def delete_page(page_id: UUID, session=Session):
        item = await session.get(StatusPage, page_id)
        if item is None:
            raise HTTPException(404, "Status page not found")
        await session.delete(item)

    @app.get("/api/v1/public/status-pages/{slug}", response_model=PublicPage)
    async def public_page(slug: str, session=Session):
        item = await session.scalar(
            select(StatusPage).where(StatusPage.slug == slug, StatusPage.published.is_(True))
        )
        if item is None:
            raise HTTPException(404, "Status page not found")
        monitors = (
            await session.scalars(
                select(Monitor).where(
                    Monitor.id.in_(item.monitor_ids), Monitor.deleted_at.is_(None)
                )
            )
        ).all()
        output = []
        for monitor in monitors:
            stats = await summary(session, now() - timedelta(days=30), now(), monitor.id)
            incidents = (
                await session.scalars(
                    select(Incident)
                    .where(Incident.monitor_id == monitor.id)
                    .order_by(Incident.started_at.desc())
                    .limit(10)
                )
            ).all()
            output.append(
                {
                    "name": monitor.name,
                    "status": monitor.status,
                    "uptime": stats["uptime"],
                    "last_checked_at": monitor.last_checked_at,
                    "incidents": [
                        {"state": i.state, "started_at": i.started_at, "resolved_at": i.resolved_at}
                        for i in incidents
                    ],
                }
            )
        dates = [m.last_checked_at for m in monitors if m.last_checked_at]
        return {
            "name": item.name,
            "description": item.description,
            "updated_at": max(dates) if dates else None,
            "monitors": output,
        }
