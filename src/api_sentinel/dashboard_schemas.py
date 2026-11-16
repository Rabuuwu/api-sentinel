from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from api_sentinel.vault import validate_webhook


class ChannelInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    provider: Literal["discord"] = "discord"
    webhook_url: SecretStr
    enabled: bool = True
    on_down: bool = True
    on_recovered: bool = True

    @field_validator("webhook_url")
    @classmethod
    def webhook(cls, value: SecretStr) -> SecretStr:
        validate_webhook(value.get_secret_value())
        return value


class ChannelPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    enabled: bool | None = None
    on_down: bool | None = None
    on_recovered: bool | None = None
    # Rotate by creating a new channel; never edit a secret outside its DB transaction.


class ChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    provider: str
    enabled: bool
    on_down: bool
    on_recovered: bool
    created_at: datetime


class StatusPageInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str = Field(default="", max_length=1000)
    published: bool = False
    monitor_ids: list[UUID] = Field(min_length=1, max_length=100)


class MetricSummary(BaseModel):
    total: int = 0
    successful: int = 0
    failed: int = 0
    degraded: int = 0
    uptime: float | None = None
    average_ms: float | None = None
    p50: float | None = None
    p75: float | None = None
    p90: float | None = None
    p95: float | None = None
    p99: float | None = None


class MetricBucket(MetricSummary):
    at: datetime
    until: datetime


class MetricsOut(BaseModel):
    monitor_id: UUID
    window: str
    start: datetime
    end: datetime
    summary: MetricSummary
    previous: MetricSummary | None
    buckets: list[MetricBucket]
    latency_series: list[str]


class PublicIncident(BaseModel):
    state: str
    started_at: datetime
    resolved_at: datetime | None


class PublicMonitor(BaseModel):
    name: str
    status: str
    uptime: float | None
    last_checked_at: datetime | None
    incidents: list[PublicIncident]


class PublicPage(BaseModel):
    name: str
    description: str
    updated_at: datetime | None
    monitors: list[PublicMonitor]
