"""Typed domain error classes."""

class OpsMemoryError(Exception):
    """Base exception for all OpsMemory errors."""
    def __init__(self, message: str, status_code: int = 500, details: dict = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class AuthenticationError(OpsMemoryError):
    """Raised when tenant API key is invalid or missing."""
    def __init__(self, message: str = "Invalid or missing tenant credentials"):
        super().__init__(message, status_code=401)


class TenantNotFoundError(OpsMemoryError):
    """Raised when tenant does not exist."""
    def __init__(self, message: str = "Tenant not found"):
        super().__init__(message, status_code=404)


class TenantIsolationError(OpsMemoryError):
    """Raised when a cross-tenant access violation is detected."""
    def __init__(self, message: str = "Cross-tenant access prohibited"):
        super().__init__(message, status_code=403)


class ResourceNotFoundError(OpsMemoryError):
    """Raised when an entity, memory, or task is not found."""
    def __init__(self, message: str = "Requested resource not found"):
        super().__init__(message, status_code=404)


class ConflictError(OpsMemoryError):
    """Raised when an optimistic concurrency update fails or contradictory state occurs."""
    def __init__(self, message: str = "Version conflict or concurrent modification detected"):
        super().__init__(message, status_code=409)


class TaskClaimError(OpsMemoryError):
    """Raised when claiming a task that is already claimed or no longer pending."""
    def __init__(self, message: str = "Task could not be claimed"):
        super().__init__(message, status_code=409)


class DatabaseUnavailableError(OpsMemoryError):
    """Raised when database or graph backend is unreachable."""
    def __init__(self, message: str = "Database service temporarily unavailable"):
        super().__init__(message, status_code=503)


class LLMUnavailableError(OpsMemoryError):
    """Raised when the requested LLM provider fails or is unreachable."""
    def __init__(self, message: str = "LLM provider temporarily unavailable"):
        super().__init__(message, status_code=503)


class ValidationError(OpsMemoryError):
    """Raised when domain validation fails."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, status_code=422, details=details)
