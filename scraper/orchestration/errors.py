"""Typed Error Hierarchy and ADGO Failure Classification (§13, DS-A34)."""


class DeepSearchError(Exception):
    """Base exception for all DeepSearch errors."""

    def __init__(
        self,
        message: str,
        failure_class: str = "permanent",
        retry_after_seconds: float = 0.0,
    ):
        super().__init__(message)
        self.message = message
        self.failure_class = failure_class
        self.retry_after_seconds = retry_after_seconds


class TransientFailure(DeepSearchError):
    """Transient error suitable for immediate or exponential backoff retry."""

    def __init__(self, message: str, retry_after_seconds: float = 1.0):
        super().__init__(
            message, failure_class="transient", retry_after_seconds=retry_after_seconds
        )


class RateLimitFailure(DeepSearchError):
    """Rate limit (429) error requiring explicit retry-after backoff."""

    def __init__(self, message: str, retry_after_seconds: float = 5.0):
        super().__init__(
            message, failure_class="rate_limit", retry_after_seconds=retry_after_seconds
        )


class InvalidInputFailure(DeepSearchError):
    """Client error or invalid configuration that cannot succeed on retry."""

    def __init__(self, message: str):
        super().__init__(
            message, failure_class="invalid_input", retry_after_seconds=0.0
        )


class QualityFailure(DeepSearchError):
    """Content extracted failed minimum quality threshold (e.g. empty JS shell)."""

    def __init__(self, message: str):
        super().__init__(message, failure_class="quality", retry_after_seconds=0.0)


class PermanentFailure(DeepSearchError):
    """Unrecoverable error (e.g. 404/410 HTTP, unsupported format)."""

    def __init__(self, message: str):
        super().__init__(message, failure_class="permanent", retry_after_seconds=0.0)


class SecurityFailure(DeepSearchError):
    """Security policy violation (e.g. SSRF block, private subnet probe)."""

    def __init__(self, message: str):
        super().__init__(message, failure_class="permanent", retry_after_seconds=0.0)


class BudgetFailure(DeepSearchError):
    """Budget limit exhausted for the execution."""

    def __init__(self, message: str):
        super().__init__(message, failure_class="permanent", retry_after_seconds=0.0)


class AmbiguousSideEffectFailure(DeepSearchError):
    """Error occurred during/after external write where state is ambiguous."""

    def __init__(self, message: str):
        super().__init__(
            message, failure_class="ambiguous_side_effect", retry_after_seconds=0.0
        )


def map_exception_to_failure(exc: Exception) -> tuple[str, float]:
    """Maps an arbitrary Python exception to an ADGO failure class and retry delay."""
    if isinstance(exc, DeepSearchError):
        return exc.failure_class, exc.retry_after_seconds

    # Timeout / connection errors
    exc_name = type(exc).__name__.lower()
    msg = str(exc).lower()

    if "timeout" in exc_name or "timeout" in msg:
        return "transient", 2.0
    if "connect" in exc_name or "connection" in msg or "network" in msg:
        return "transient", 1.0
    if "429" in msg or "rate" in msg:
        return "rate_limit", 5.0
    if "ssrf" in msg or "security" in msg:
        return "permanent", 0.0

    return "permanent", 0.0
