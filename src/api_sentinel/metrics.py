"""Bounded PostgreSQL aggregates. Missing measurements remain explicitly unknown."""

from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import func, select

from api_sentinel.models import Execution, Monitor

Window = Literal["24h", "7d", "30d"]
WINDOW_DAYS = {"24h": 1, "7d": 7, "30d": 30}
SUCCESS = ("SUCCESS", "DEGRADED")
PERCENTILES = (50, 75, 90, 95, 99)


def rate(successful: int, total: int) -> float | None:
    return round(successful / total * 100, 3) if total else None


def percentile(values: list[float], percent: float) -> float | None:
    """Reference implementation matching PostgreSQL percentile_cont, used in tests."""
    if not values:
        return None
    data = sorted(values)
    position = (len(data) - 1) * percent / 100
    lower = int(position)
    upper = min(lower + 1, len(data) - 1)
    return data[lower] + (data[upper] - data[lower]) * (position - lower)


def aggregates():
    return [
        func.min(Execution.finished_at).label("first_check_at"),
        func.max(Execution.finished_at).label("last_check_at"),
        func.count().label("total"),
        func.count().filter(Execution.result.in_(SUCCESS)).label("successful"),
        func.count().filter(Execution.result == "DEGRADED").label("degraded"),
        func.avg(Execution.latency_ms).filter(Execution.result.in_(SUCCESS)).label("average_ms"),
        *[
            func.percentile_cont(p / 100)
            .within_group(Execution.latency_ms)
            .filter(Execution.result.in_(SUCCESS))
            .label(f"p{p}")
            for p in PERCENTILES
        ],
    ]


def serialize_summary(row) -> dict:
    data = dict(row)
    data["failed"] = data["total"] - data["successful"]
    data["uptime"] = rate(data["successful"], data["total"])
    return data


async def summary(session, start, end, monitor_id=None, owner_id=None):
    query = (
        select(*aggregates())
        .select_from(Execution)
        .where(
            Execution.finished_at >= start,
            Execution.finished_at < end,
            Execution.result != "ABORTED",
        )
    )
    if monitor_id is not None:
        query = query.where(Execution.monitor_id == monitor_id)
    else:
        query = query.join(Monitor).where(Monitor.deleted_at.is_(None))
        if owner_id is not None:
            query = query.where(Monitor.owner_id == owner_id)
    row = (await session.execute(query)).mappings().one()
    return serialize_summary(row)


def history_info(stats, start, end, retention_days):
    return {
        "requested_start": start, "requested_end": end,
        "retention_days": retention_days,
        "retention_limited": end - start > timedelta(days=retention_days),
        "first_check_at": stats.get("first_check_at"),
        "last_check_at": stats.get("last_check_at"),
        "completed_checks": stats["total"],
    }


def comparable(current, previous, start, end, retention_days, interval):
    duration = end - start
    if duration * 2 > timedelta(days=retention_days):
        return False
    tolerance = timedelta(seconds=interval * 2 + 30)
    for stats, left, right in ((current, start, end), (previous, start-duration, start)):
        if (not stats["total"] or stats["first_check_at"] > left + tolerance
                or stats["last_check_at"] < right - tolerance
                or stats["total"] < duration.total_seconds() / interval * 0.9):
            return False
    return True


async def metrics(session, monitor_id, window: Window, end: datetime, retention_days=30):
    duration = timedelta(days=WINDOW_DAYS[window])
    start = end - duration
    current = await summary(session, start, end, monitor_id)
    previous = await summary(session, start - duration, start, monitor_id)
    monitor = await session.get(Monitor, monitor_id)
    compare = comparable(current, previous, start, end, retention_days, monitor.interval_seconds)
    width = duration.total_seconds() / 60
    slot = func.floor((func.extract("epoch", Execution.finished_at) - start.timestamp()) / width)
    query = (
        select(slot.label("slot"), *aggregates())
        .where(
            Execution.monitor_id == monitor_id,
            Execution.finished_at >= start,
            Execution.finished_at < end,
            Execution.result != "ABORTED",
        )
        .group_by(slot)
        .order_by(slot)
    )
    rows = {
        int(row["slot"]): serialize_summary(row)
        for row in (await session.execute(query)).mappings()
    }
    buckets = []
    for index in range(60):
        point = rows.get(
            index,
            {
                "total": 0,
                "successful": 0,
                "failed": 0,
                "degraded": 0,
                "uptime": None,
                "average_ms": None,
            },
        )
        buckets.append(
            {
                "at": start + timedelta(seconds=width * index),
                "until": start + timedelta(seconds=width * (index + 1)),
                **point,
            }
        )
    return {
        "monitor_id": monitor_id,
        "window": window,
        "start": start,
        "end": end,
        "summary": current,
        "previous": previous if compare else None,
        "comparison_available": compare,
        "history": history_info(current, start, end, retention_days),
        "buckets": buckets,
        "latency_series": ["average_ms"],
    }
