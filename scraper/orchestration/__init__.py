"""Axiom ADGO durable orchestration integration for DeepSearch."""

from scraper.orchestration.axiom_client import AxiomClient
from scraper.orchestration.axiom_worker import AxiomRemoteWorker
from scraper.orchestration.errors import (
    BudgetFailure,
    DeepSearchError,
    PermanentFailure,
    QualityFailure,
    RateLimitFailure,
    SecurityFailure,
    TransientFailure,
)
from scraper.orchestration.protocol import (
    ActivityResult,
    RemoteFailure,
    RemoteWorkItem,
    ResourceUsage,
    WorkerSpec,
    WorkToken,
)
from scraper.orchestration.registry import ActivityRegistry, activity_registry

__all__ = [
    "ActivityRegistry",
    "ActivityResult",
    "AxiomClient",
    "AxiomRemoteWorker",
    "BudgetFailure",
    "DeepSearchError",
    "PermanentFailure",
    "QualityFailure",
    "RateLimitFailure",
    "RemoteFailure",
    "RemoteWorkItem",
    "ResourceUsage",
    "SecurityFailure",
    "TransientFailure",
    "WorkToken",
    "WorkerSpec",
    "activity_registry",
]
