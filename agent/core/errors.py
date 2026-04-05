"""Domain-specific exceptions."""

from __future__ import annotations


class ConfigManagerError(Exception):
    """Base exception for all config manager errors."""


class ValidationError(ConfigManagerError):
    """Raised when a revision fails validation."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors) if errors else "validation failed")


class RevisionNotFoundError(ConfigManagerError):
    """Raised when a requested revision does not exist."""


class ApplyError(ConfigManagerError):
    """Raised when the apply pipeline cannot complete."""


class HealthCheckError(ApplyError):
    """Raised when a post-apply health check fails."""


class NoActiveRevisionError(ConfigManagerError):
    """Raised when no active revision is available for rollback."""
