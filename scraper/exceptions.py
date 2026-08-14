"""Core Exception Taxonomy for DeepSearch Platform."""

class DeepSearchError(Exception):
    """Base exception for all DeepSearch platform errors."""
    pass


class AcquisitionError(DeepSearchError):
    """Raised when page or content acquisition fails."""
    pass


class SSRFError(AcquisitionError):
    """Raised when a request target resolves to a forbidden or private IP address."""
    pass


class BrowserPoolError(AcquisitionError):
    """Raised when browser pool initialization, allocation, or execution fails."""
    pass


class StorageError(DeepSearchError):
    """Raised during storage persistence or retrieval operations."""
    pass


class ContractViolationError(DeepSearchError):
    """Raised when inter-module data contracts or invariants are violated."""
    pass


class BudgetExceededError(DeepSearchError):
    """Raised when crawl job budget limits (pages, bytes, time, tokens) are exceeded."""
    pass
