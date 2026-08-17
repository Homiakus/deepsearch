"""Protocol models for Axiom ADGO Remote Worker Protocol (DS-A06, DS-A34, DS-A35)."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class WorkToken(BaseModel):
    executionId: str
    taskId: str
    workerId: str
    attempt: int


class WorkerSpec(BaseModel):
    id: str
    activities: List[str] = Field(default_factory=list)
    concurrency: int = 4
    leaseTTL: int = 30_000_000_000  # 30 seconds in nanoseconds
    pollInterval: int = 100_000_000  # 100 milliseconds in nanoseconds


class RemoteNode(BaseModel):
    id: str
    kind: str
    activity: Optional[str] = None
    capability: Optional[str] = None
    risk: Optional[int] = None
    timeout: Optional[int] = None


class RemoteActivityRequest(BaseModel):
    executionId: Optional[str] = None
    nodeId: Optional[str] = None
    attempt: Optional[int] = 1
    input: Dict[str, Any] = Field(default_factory=dict)


class RemoteWorkItem(BaseModel):
    token: WorkToken
    node: RemoteNode
    activity: str
    provider: Optional[str] = None
    request: Optional[RemoteActivityRequest] = None
    leaseUntil: Optional[datetime] = None
    score: Optional[float] = 0.0


class ResourceUsage(BaseModel):
    cost: float = 0.0
    tokens: int = 0
    activeDurationNanos: int = 0
    llmCalls: int = 0
    searchQueries: int = 0
    browserFetches: int = 0


class ActivityResult(BaseModel):
    data: Dict[str, Any] = Field(default_factory=dict)
    usage: Optional[ResourceUsage] = Field(default_factory=ResourceUsage)
    quality: Dict[str, float] = Field(default_factory=dict)


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
    details: Dict[str, Any] = Field(default_factory=dict)
