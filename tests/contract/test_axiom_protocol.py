"""Contract tests for Axiom ADGO Remote Worker Protocol (DS-A06, DS-A34, DS-A35)."""

from scraper.orchestration.errors import (
    QualityFailure,
    RateLimitFailure,
    TransientFailure,
    map_exception_to_failure,
)
from scraper.orchestration.idempotency import generate_activity_idempotency_key
from scraper.orchestration.protocol import (
    ActivityResult,
    CompleteHTTPRequest,
    ResourceUsage,
    WorkToken,
)


def test_work_token_serialization():
    token = WorkToken(
        executionId="exec-123",
        taskId="task-456",
        workerId="py-worker-1",
        attempt=2,
    )
    dumped = token.model_dump()
    assert dumped["executionId"] == "exec-123"
    assert dumped["taskId"] == "task-456"
    assert dumped["workerId"] == "py-worker-1"
    assert dumped["attempt"] == 2


def test_complete_request_serialization():
    token = WorkToken(executionId="e1", taskId="t1", workerId="w1", attempt=1)
    result = ActivityResult(
        data={"clean_text": "Extracted text content"},
        usage=ResourceUsage(cost=0.05, tokens=150),
        quality={"completeness": 0.95},
    )
    req = CompleteHTTPRequest(token=token, result=result, durationNanos=50_000_000)
    data = req.model_dump()
    assert data["token"]["executionId"] == "e1"
    assert data["result"]["data"]["clean_text"] == "Extracted text content"
    assert data["durationNanos"] == 50000000


def test_failure_classification_mapping():
    c, delay = map_exception_to_failure(
        TransientFailure("Connection reset", retry_after_seconds=2.5)
    )
    assert c == "transient"
    assert delay == 2.5

    c2, delay2 = map_exception_to_failure(
        RateLimitFailure("429 Too Many Requests", retry_after_seconds=10.0)
    )
    assert c2 == "rate_limit"
    assert delay2 == 10.0

    c3, _ = map_exception_to_failure(QualityFailure("Empty body"))
    assert c3 == "quality"


def test_idempotency_key_generation():
    key1 = generate_activity_idempotency_key(
        "exec-1", "NormalizeQuery", {"query": "deep search"}
    )
    key2 = generate_activity_idempotency_key(
        "exec-1", "NormalizeQuery", {"query": "deep search"}
    )
    key3 = generate_activity_idempotency_key(
        "exec-1", "NormalizeQuery", {"query": "other query"}
    )

    assert key1 == key2
    assert key1 != key3
    assert key1.startswith("exec-1:NormalizeQuery:r1:")
