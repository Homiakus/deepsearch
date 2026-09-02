"""Protocol models for Axiom ADGO Remote Worker Protocol (DS-A06, DS-A34, DS-A35)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkToken(BaseModel):
    executionId: str
    taskId: str
    workerId: str
    attempt: int


class WorkerSpec(BaseModel):
    id: str
    activities: list[str] = Field(default_factory=list)
    concurrency: int = 4
    leaseTTL: int = 30_000_000_000  # 30 seconds in nanoseconds
    pollInterval: int = 100_000_000  # 100 milliseconds in nanoseconds


class RemoteNode(BaseModel):
    id: str
    kind: str
    activity: str | None = None
    capability: str | None = None
    risk: int | None = None
    timeout: int | None = None


class RemoteActivityRequest(BaseModel):
    executionId: str | None = None
    nodeId: str | None = None
    attempt: int | None = 1
    input: dict[str, Any] = Field(default_factory=dict)


class RemoteWorkItem(BaseModel):
    token: WorkToken
    node: RemoteNode
    activity: str
    provider: str | None = None
    request: RemoteActivityRequest | None = None
    leaseUntil: datetime | None = None
    score: float | None = 0.0


class ResourceUsage(BaseModel):
    cost: float = 0.0
    tokens: int = 0
    activeDurationNanos: int = 0
    llmCalls: int = 0
    searchQueries: int = 0
    browserFetches: int = 0


class ActivityResult(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
    usage: ResourceUsage | None = Field(default_factory=ResourceUsage)
    quality: dict[str, float] = Field(default_factory=dict)


class RemoteFailure(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    failure_class: str = Field(default="transient", alias="class")
    message: str
    retryAfterNanos: int = 0


class CompleteHTTPRequest(BaseModel):
    token: WorkToken
    result: ActivityResult
    durationNanos: int = 0


class FailHTTPRequest(BaseModel):
    token: WorkToken
    failure: RemoteFailure
    durationNanos: int = 0


class HeartbeatHTTPRequest(BaseModel):
    token: WorkToken
    details: dict[str, Any] = Field(default_factory=dict)
