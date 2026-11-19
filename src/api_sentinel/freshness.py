"""Derived observation freshness; never changes the incident state machine."""
from datetime import timedelta


def observation(monitor, at):
    threshold = 2 * monitor.interval_seconds + monitor.timeout_seconds + 30
    last = monitor.last_checked_at
    if monitor.status == "PAUSED":
        freshness = "PAUSED"
    elif last is None:
        freshness = "AWAITING"
    elif last > at or at - last > timedelta(seconds=threshold):
        freshness = "STALE"
    else:
        freshness = "FRESH"
    return {
        "freshness": freshness,
        "last_observed_status": monitor.status,
        "effective_status": monitor.status if freshness in ("FRESH", "PAUSED") else "UNKNOWN",
        "stale_after_seconds": threshold,
    }
