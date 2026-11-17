import base64
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from sqlalchemy import String, cast, func, or_, select, text, tuple_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from api_sentinel.auth import install_auth, owned_monitors, owner
from api_sentinel.auth_models import AuthSession, User
from api_sentinel.config import Settings
from api_sentinel.dashboard import install_dashboard, validate_channels
from api_sentinel.db import Database
from api_sentinel.metrics import SUCCESS
from api_sentinel.middleware import BodyLimitMiddleware
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
from api_sentinel.schemas import MonitorInput, MonitorPatch

STATIC = Path(__file__).parent / "static"
logger = logging.getLogger("sentinel")


def as_dict(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def encode_cursor(row, field):
    data = [getattr(row, field).isoformat(), str(row.id)]
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()


def decode_cursor(value: str):
    try:
        stamp, key = json.loads(base64.b64decode(value, altchars=b"-_", validate=True))
        stamp = datetime.fromisoformat(stamp)
        if stamp.tzinfo is None:
            raise ValueError
        return stamp, UUID(key)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(400, "Invalid cursor") from exc


async def page(session, statement, model, field, limit, cursor):
    column = getattr(model, field)
    if cursor:
        stamp, key = decode_cursor(cursor)
        statement = statement.where(tuple_(column, model.id) < tuple_(stamp, key))
    rows = list(
        (
            await session.scalars(
                statement.order_by(column.desc(), model.id.desc()).limit(limit + 1)
            )
        ).all()
    )
    return {
        "items": [as_dict(r) for r in rows[:limit]],
        "next_cursor": encode_cursor(rows[limit - 1], field) if len(rows) > limit else None,
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    db = Database(settings)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await db.close()

    app = FastAPI(
        title="API Sentinel",
        version="0.2.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.db = db
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    # Bounded process-wide request budget; authentication has a separate persisted budget.
    budget = {"start": time.monotonic(), "count": 0}

    def failure(request, status, message, code=None):
        codes = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            404: "NOT_FOUND",
            409: "CONFLICT",
            422: "VALIDATION_ERROR",
            429: "RATE_LIMITED",
            503: "UNAVAILABLE",
        }
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": code or codes.get(status, "INTERNAL_ERROR"),
                    "message": message,
                    "request_id": getattr(request.state, "request_id", "unknown"),
                }
            },
        )

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        request.state.request_id = str(uuid4())
        if request.url.path.startswith("/api/"):
            current = time.monotonic()
            if current - budget["start"] >= 60:
                budget.update(start=current, count=0)
            budget["count"] += 1
            if budget["count"] > 300:
                return failure(request, 429, "Request limit exceeded; retry in one minute")
            length = request.headers.get("content-length")
            if length and (not length.isdigit() or int(length) > 16384):
                return failure(request, 413, "Request body too large", "BODY_TOO_LARGE")
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        return failure(request, exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Do not echo input values, URLs or credentials into errors/logs.
        return failure(request, 422, "Invalid request fields or parameters")

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        logger.error(
            json.dumps(
                {
                    "event": "database_error",
                    "request_id": request.state.request_id,
                    "error_type": type(exc).__name__,
                }
            )
        )
        return failure(request, 503, "Database unavailable; check the local PostgreSQL service")

    @app.exception_handler(IntegrityError)
    async def conflict(request, exc):
        return failure(request, 409, "This change conflicts with an existing record")

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        logger.error(
            json.dumps(
                {
                    "event": "request_error",
                    "error_type": type(exc).__name__,
                    "request_id": getattr(request.state, "request_id", "unknown"),
                }
            )
        )
        return failure(request, 500, "Unexpected server error")

    auth = install_auth(app, db, settings)

    async def public_session_dependency():
        async with db.sessions.begin() as session:
            yield session

    Auth = Depends(auth)

    async def session_dependency(user=Auth):
        async with db.sessions.begin() as session:
            session.info["user_id"] = user.id
            yield session

    router = APIRouter(prefix="/api/v1", dependencies=[Depends(auth)])
    Session = Depends(session_dependency, scope="function")
    PublicSession = Depends(public_session_dependency, scope="function")
    app.state.session_dependency = session_dependency

    async def get_monitor(session, key, lock=False):
        statement = select(Monitor).where(
            Monitor.id == key, Monitor.deleted_at.is_(None), Monitor.owner_id == owner(session)
        )
        monitor = await session.scalar(statement.with_for_update() if lock else statement)
        if monitor is None:
            raise HTTPException(404, "Monitor not found")
        return monitor

    @router.get("/openapi.json")
    async def openapi():
        return app.openapi()

    @router.post("/monitors", status_code=201)
    async def create_monitor(data: MonitorInput, session=Session):
        await session.execute(text("SELECT pg_advisory_xact_lock(71424002)"))
        count = await session.scalar(
            select(func.count()).select_from(Monitor).where(Monitor.deleted_at.is_(None))
        )
        if count >= settings.max_monitors:
            raise HTTPException(409, "Monitor limit reached")
        await validate_channels(session, data.notification_channel_ids)
        monitor = Monitor(owner_id=owner(session), **data.model_dump())
        session.add(monitor)
        await session.flush()
        session.add(MonitorEvent(monitor_id=monitor.id, action="MONITOR_CREATED"))
        return as_dict(monitor)

    @router.get("/monitors")
    async def monitors(
        status: Literal["UNKNOWN", "UP", "DEGRADED", "DOWN", "PAUSED"] | None = None,
        limit: int = Query(20, ge=1, le=100),
        cursor: str | None = Query(None, max_length=256),
        session=Session,
    ):
        statement = select(Monitor).where(
            Monitor.deleted_at.is_(None), Monitor.owner_id == owner(session)
        )
        if status:
            statement = statement.where(Monitor.status == status)
        return await page(session, statement, Monitor, "created_at", limit, cursor)

    @router.get("/monitors/{monitor_id}")
    async def detail(monitor_id: UUID, session=Session):
        return as_dict(await get_monitor(session, monitor_id))

    @router.patch("/monitors/{monitor_id}")
    async def edit(monitor_id: UUID, data: MonitorPatch, session=Session):
        monitor = await get_monitor(session, monitor_id, True)
        values = {k: getattr(monitor, k) for k in MonitorInput.model_fields}
        values.update(data.model_dump(exclude_unset=True))
        try:
            validated = MonitorInput.model_validate(values)
        except ValidationError as exc:
            raise HTTPException(422, "Invalid monitor configuration") from exc
        # Keep an incident tied to the target that caused it.
        open_incident = await session.scalar(
            select(Incident.id).where(Incident.monitor_id == monitor_id, Incident.state == "OPEN")
        )
        if open_incident and validated.url != monitor.url:
            raise HTTPException(409, "Resolve the open incident before changing its target URL")
        await validate_channels(session, validated.notification_channel_ids)
        target_changed = validated.url != monitor.url
        for key, value in validated.model_dump().items():
            setattr(monitor, key, value)
        monitor.generation += 1
        monitor.consecutive_failures = monitor.consecutive_successes = 0
        monitor.consecutive_degraded = 0
        monitor.failure_started_at = None
        monitor.next_run_at = now()
        if target_changed:
            monitor.status = "PAUSED" if monitor.paused_at else "UNKNOWN"
            monitor.last_checked_at = None
        session.add(MonitorEvent(monitor_id=monitor.id, action="MONITOR_UPDATED"))
        await session.flush()
        return as_dict(monitor)

    async def change_pause(session, monitor_id, pause):
        monitor = await get_monitor(session, monitor_id, True)
        if bool(monitor.paused_at) == pause:
            return as_dict(monitor)
        monitor.generation += 1
        monitor.consecutive_failures = monitor.consecutive_successes = 0
        monitor.consecutive_degraded = 0
        monitor.failure_started_at = None
        monitor.paused_at = now() if pause else None
        incident = await session.scalar(
            select(Incident.id).where(Incident.monitor_id == monitor_id, Incident.state == "OPEN")
        )
        monitor.status = "PAUSED" if pause else ("DOWN" if incident else "UNKNOWN")
        monitor.next_run_at = now()
        session.add(
            MonitorEvent(
                monitor_id=monitor.id, action="MONITOR_PAUSED" if pause else "MONITOR_RESUMED"
            )
        )
        await session.flush()
        return as_dict(monitor)

    @router.post("/monitors/{monitor_id}/pause")
    async def pause(monitor_id: UUID, session=Session):
        return await change_pause(session, monitor_id, True)

    @router.post("/monitors/{monitor_id}/resume")
    async def resume(monitor_id: UUID, session=Session):
        return await change_pause(session, monitor_id, False)

    @router.delete("/monitors/{monitor_id}", status_code=204)
    async def remove(monitor_id: UUID, session=Session):
        monitor = await get_monitor(session, monitor_id, True)
        # Soft deletion is not a recovery: retain the last known incident state for audit.
        monitor.deleted_at = now()
        monitor.generation += 1

    @router.get("/monitors/{monitor_id}/checks")
    async def checks(
        monitor_id: UUID,
        limit: int = Query(50, ge=1, le=100),
        cursor: str | None = Query(None, max_length=256),
        session=Session,
    ):
        await get_monitor(session, monitor_id)
        return await page(
            session,
            select(Execution).where(
                Execution.monitor_id == monitor_id, Execution.finished_at.is_not(None)
            ),
            Execution,
            "finished_at",
            limit,
            cursor,
        )

    @router.get("/monitors/{monitor_id}/incidents")
    async def incidents(
        monitor_id: UUID,
        state: Literal["open", "resolved"] | None = None,
        limit: int = Query(50, ge=1, le=100),
        cursor: str | None = Query(None, max_length=256),
        session=Session,
    ):
        await get_monitor(session, monitor_id)
        statement = select(Incident).where(Incident.monitor_id == monitor_id)
        if state:
            statement = statement.where(Incident.state == state.upper())
        return await page(session, statement, Incident, "created_at", limit, cursor)

    @router.get("/incidents/{incident_id}")
    async def incident_detail(incident_id: UUID, session=Session):
        incident = await session.scalar(
            select(Incident).where(
                Incident.id == incident_id, Incident.monitor_id.in_(owned_monitors(session))
            )
        )
        if incident is None:
            raise HTTPException(404, "Incident not found")
        return as_dict(incident)

    @router.get("/monitors/{monitor_id}/stats")
    async def stats(monitor_id: UUID, window: Literal["24h", "7d", "30d"] = "24h", session=Session):
        await get_monitor(session, monitor_id)
        cutoff = now() - timedelta(days={"24h": 1, "7d": 7, "30d": 30}[window])
        base = [
            Execution.monitor_id == monitor_id,
            Execution.finished_at >= cutoff,
            Execution.result != "ABORTED",
        ]
        completed, successful = (
            await session.execute(
                select(func.count(), func.count().filter(Execution.result.in_(SUCCESS)))
                .select_from(Execution)
                .where(*base)
            )
        ).one()
        p50, p95 = (
            await session.execute(
                select(
                    func.percentile_cont(0.5).within_group(Execution.latency_ms),
                    func.percentile_cont(0.95).within_group(Execution.latency_ms),
                ).where(*base, Execution.result.in_(SUCCESS))
            )
        ).one()
        aborted = await session.scalar(
            select(func.count())
            .select_from(Execution)
            .where(
                Execution.monitor_id == monitor_id,
                Execution.finished_at >= cutoff,
                Execution.result == "ABORTED",
            )
        )
        opened = await session.scalar(
            select(func.count())
            .select_from(Incident)
            .where(Incident.monitor_id == monitor_id, Incident.state == "OPEN")
        )
        return {
            "monitor_id": monitor_id,
            "window": window,
            "completed_checks": completed,
            "successful_checks": successful,
            "aborted_checks": aborted,
            "success_rate_percent": round(successful / completed * 100, 2) if completed else None,
            "latency_p50_ms": p50,
            "latency_p95_ms": p95,
            "open_incidents": opened,
        }

    @router.get("/system")
    async def system(session=Session):
        heartbeat = await session.get(WorkerHeartbeat, 1)
        fresh = bool(heartbeat and now() - heartbeat.updated_at < timedelta(seconds=90))
        own_alert = or_(
            Alert.incident_id.in_(
                select(Incident.id).where(Incident.monitor_id.in_(owned_monitors(session)))
            ),
            Alert.channel.in_(
                select("discord:" + cast(NotificationChannel.id, String)).where(
                    NotificationChannel.owner_id == owner(session)
                )
            ),
        )
        pending = await session.scalar(
            select(func.count())
            .select_from(Alert)
            .where(Alert.delivery_state == "PENDING", own_alert)
        )
        failed = await session.scalar(
            select(func.count())
            .select_from(Alert)
            .where(Alert.delivery_state == "FAILED", own_alert)
        )
        return {
            "version": "0.2.0",
            "location": "Render" if settings.hosted else "Self-hosted",
            "hosting_notice": (
                "Free hosting may sleep. Measurements stop while the service is asleep."
                if settings.hosted
                else None
            ),
            "retention_days": settings.retention_days,
            "max_monitors": settings.max_monitors,
            "worker_alive": fresh,
            "worker_last_seen": heartbeat.updated_at if heartbeat else None,
            "pending_alerts": pending,
            "failed_alerts": failed,
            "alert_channel": "per-monitor channels (console when unassigned)",
        }

    install_dashboard(app, router, Session, get_monitor, page, as_dict, settings, PublicSession)
    app.include_router(router)

    @app.get("/health/live")
    async def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready():
        async with db.sessions() as session:
            await session.execute(select(Monitor).limit(1))
            await session.execute(select(NotificationChannel).limit(1))
            await session.execute(select(User.id).limit(1))
            await session.execute(select(AuthSession.token_hash).limit(1))
        return {"status": "ready"}

    @app.get("/legacy", include_in_schema=False)
    async def index():
        raise HTTPException(410, "Legacy API-key dashboard retired; use the account dashboard")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str):
        if path.startswith(("api/", "health/")):
            raise HTTPException(404, "Not found")
        root = Path(settings.frontend_dir).resolve()
        candidate = (root / path).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            return FileResponse(candidate)
        if not (root / "index.html").is_file():
            raise HTTPException(
                503, "React frontend not built; run npm install and npm run build in frontend/"
            )
        return FileResponse(root / "index.html")

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
            expose_headers=["X-Request-ID"],
            max_age=600,
        )
    return app
