"""Axiom ADGO durable orchestration integration for DeepSearch."""

from scraper.orchestration.protocol import (
    WorkToken,
    WorkerSpec,
    RemoteWorkItem,
    ActivityResult,
    RemoteFailure,
    ResourceUsage,
)
from scraper.orchestration.axiom_client import AxiomClient
from scraper.orchestration.axiom_worker import AxiomRemoteWorker
from scraper.orchestration.registry import ActivityRegistry, activity_registry
from scraper.orchestration.errors import (
    DeepSearchError,
    TransientFailure,
    RateLimitFailure,
    QualityFailure,
    PermanentFailure,
    SecurityFailure,
    BudgetFailure,
)

__all__ = [
    "WorkToken",
    "WorkerSpec",
    "RemoteWorkItem",
    "ActivityResult",
    "RemoteFailure",
    "ResourceUsage",
    "AxiomClient",
    "AxiomRemoteWorker",
    "ActivityRegistry",
    "activity_registry",
    "DeepSearchError",
    "TransientFailure",
    "RateLimitFailure",
    "QualityFailure",
    "PermanentFailure",
    "SecurityFailure",
    "BudgetFailure",
]
