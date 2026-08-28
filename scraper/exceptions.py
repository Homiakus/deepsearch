"""Core Exception Taxonomy and Error Codes for DeepSearch Platform (§DS-05)."""

from enum import Enum
from typing import Optional, Dict, Any


class ErrorCode(str, Enum):
    """Closed taxonomy of DeepSearch platform error codes (§DS-05)."""

    INVALID_INPUT = "invalid_input"
    BLOCKED_TARGET = "blocked_target"
    TIMEOUT = "timeout"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    BUDGET_EXCEEDED = "budget_exceeded"
    PARTIAL_RESULT = "partial_result"
    INTERNAL_ERROR = "internal_error"


# Deterministic mapping to HTTP response status codes
ERROR_CODE_HTTP_STATUS: Dict[ErrorCode, int] = {
    ErrorCode.INVALID_INPUT: 400,
    ErrorCode.BLOCKED_TARGET: 403,
    ErrorCode.TIMEOUT: 504,
    ErrorCode.DEPENDENCY_UNAVAILABLE: 503,
    ErrorCode.BUDGET_EXCEEDED: 429,
    ErrorCode.PARTIAL_RESULT: 206,
    ErrorCode.INTERNAL_ERROR: 500,
}

# Deterministic mapping to CLI exit codes
ERROR_CODE_CLI_EXIT: Dict[ErrorCode, int] = {
    ErrorCode.INVALID_INPUT: 2,
    ErrorCode.BLOCKED_TARGET: 3,
    ErrorCode.TIMEOUT: 4,
    ErrorCode.DEPENDENCY_UNAVAILABLE: 5,
    ErrorCode.BUDGET_EXCEEDED: 6,
    ErrorCode.PARTIAL_RESULT: 7,
    ErrorCode.INTERNAL_ERROR: 1,
}


class DeepSearchError(Exception):
    """Base exception for all DeepSearch platform errors."""

    error_code: ErrorCode = ErrorCode.INTERNAL_ERROR

    def __init__(
        self,
        message: str,
        *,
        code: Optional[ErrorCode] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code or self.error_code
        self.details = details or {}

    @property
    def http_status(self) -> int:
        return ERROR_CODE_HTTP_STATUS.get(self.code, 500)

    @property
    def cli_exit_code(self) -> int:
        return ERROR_CODE_CLI_EXIT.get(self.code, 1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.code.value,
            "message": self.message,
            "details": self.details,
        }


class InvalidInputError(DeepSearchError):
    """Raised when client input, query or configuration validation fails."""

    error_code = ErrorCode.INVALID_INPUT


class BlockedTargetError(DeepSearchError):
    """Raised when request target resolves to a forbidden destination (SSRF, policy, robots deny)."""

    error_code = ErrorCode.BLOCKED_TARGET


class AcquisitionError(DeepSearchError):
    """Raised when page or content acquisition fails."""

    error_code = ErrorCode.DEPENDENCY_UNAVAILABLE


class SSRFError(BlockedTargetError):
    """Raised when a request target resolves to a forbidden or private IP address."""

    error_code = ErrorCode.BLOCKED_TARGET


SSRFBlockedError = SSRFError


class BrowserPoolError(AcquisitionError):
    """Raised when browser pool initialization, allocation, or execution fails."""

    error_code = ErrorCode.DEPENDENCY_UNAVAILABLE


class DeepSearchTimeoutError(DeepSearchError):
    """Raised when an operation exceeds its configured deadline or timeout."""

    error_code = ErrorCode.TIMEOUT


class DependencyUnavailableError(DeepSearchError):
    """Raised when an external dependency or service capability is offline/unavailable."""

    error_code = ErrorCode.DEPENDENCY_UNAVAILABLE


class StorageError(DeepSearchError):
    """Raised during storage persistence or retrieval operations."""

    error_code = ErrorCode.INTERNAL_ERROR


class ContractViolationError(DeepSearchError):
    """Raised when inter-module data contracts or invariants are violated."""

    error_code = ErrorCode.INTERNAL_ERROR


class BudgetExceededError(DeepSearchError):
    """Raised when crawl job budget limits (pages, bytes, time, tokens) are exceeded."""

    error_code = ErrorCode.BUDGET_EXCEEDED


class PartialResultError(DeepSearchError):
    """Raised when an operation yielded incomplete or degraded results."""

    error_code = ErrorCode.PARTIAL_RESULT


class InternalError(DeepSearchError):
    """Raised for unhandled internal platform failures."""

    error_code = ErrorCode.INTERNAL_ERROR
