from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from api_sentinel.security import validate_url


class MonitorInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    degraded_latency_ms: int | None = Field(default=None, ge=1, le=30000)
    degraded_threshold: int = Field(default=3, ge=1, le=100)
    notification_channel_ids: list[UUID] = Field(default_factory=list, max_length=10)
    url: str = Field(max_length=2048)
    method: Literal["GET", "HEAD"] = "GET"
    interval_seconds: int = Field(default=300, ge=60, le=86400)
    timeout_seconds: int = Field(default=20, ge=2, le=30)
    expected_status_min: int = Field(default=200, ge=100, le=599)
    expected_status_max: int = Field(default=299, ge=100, le=599)
    failure_threshold: int = Field(default=3, ge=1, le=100)
    recovery_threshold: int = Field(default=2, ge=1, le=100)
    mode: Literal["standard"] = "standard"

    @field_validator("url")
    @classmethod
    def safe_url(cls, value: str) -> str:
        return validate_url(value)

    @model_validator(mode="after")
    def valid_range(self) -> Self:
        if self.expected_status_min > self.expected_status_max:
            raise ValueError("Expected status minimum exceeds maximum")
        return self


class MonitorPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    description: str | None = None
    degraded_latency_ms: int | None = None
    degraded_threshold: int | None = None
    notification_channel_ids: list[UUID] | None = None
    url: str | None = None
    method: Literal["GET", "HEAD"] | None = None
    interval_seconds: int | None = None
    timeout_seconds: int | None = None
    expected_status_min: int | None = None
    expected_status_max: int | None = None
    failure_threshold: int | None = None
    recovery_threshold: int | None = None
    mode: Literal["standard"] | None = None
