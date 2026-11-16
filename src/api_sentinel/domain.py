from dataclasses import dataclass
from typing import Literal

Status = Literal["UNKNOWN", "UP", "DEGRADED", "DOWN", "PAUSED"]


@dataclass(frozen=True)
class Transition:
    status: str
    failures: int
    successes: int
    event: str | None = None
    degraded: int = 0


def transition(
    status: str,
    failures: int,
    successes: int,
    success: bool,
    failure_threshold: int,
    recovery_threshold: int,
    degraded: bool = False,
    degraded_count: int = 0,
    degraded_threshold: int = 3,
) -> Transition:
    """Pure state machine; a single opposite result resets the consecutive count."""
    if status == "PAUSED":
        return Transition(status, failures, successes)
    failures = 0 if success else failures + 1
    successes = successes + 1 if success and not degraded else 0
    degraded_count = degraded_count + 1 if success and degraded else 0
    if status == "DOWN":
        if success and successes >= recovery_threshold:
            return Transition("UP", failures, successes, "INCIDENT_RESOLVED", degraded_count)
    elif failures >= failure_threshold:
        return Transition("DOWN", failures, successes, "INCIDENT_OPENED")
    elif success and degraded_count >= degraded_threshold:
        event = "MONITOR_DEGRADED" if status != "DEGRADED" else None
        return Transition("DEGRADED", failures, successes, event, degraded_count)
    elif status == "DEGRADED":
        if successes >= recovery_threshold:
            return Transition("UP", failures, successes, "MONITOR_RECOVERED")
    elif success:
        status = "UP"
    return Transition(status, failures, successes, degraded=degraded_count)
