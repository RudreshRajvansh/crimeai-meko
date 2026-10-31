"""
Domain exceptions. Every error in the system maps to one of these.
FastAPI exception handlers in main.py convert them to HTTP responses.
"""
from __future__ import annotations

from typing import Any


class CrimeAIError(Exception):
    """Base exception for all application errors."""
    def __init__(self, message: str, detail: Any = None) -> None:
        self.message = message
        self.detail = detail
        super().__init__(message)


class NotFoundError(CrimeAIError):
    """Resource does not exist."""


class AlreadyExistsError(CrimeAIError):
    """Resource already exists (duplicate)."""


class AuthenticationError(CrimeAIError):
    """Invalid credentials or token."""


class AuthorizationError(CrimeAIError):
    """Authenticated but not permitted."""


class ValidationError(CrimeAIError):
    """Input data is invalid (business rule, not schema)."""


class DatabaseError(CrimeAIError):
    """Database operation failed."""


class MLServiceError(CrimeAIError):
    """Machine learning inference or training failed."""


class NLPServiceError(CrimeAIError):
    """NLP processing failed."""


class GraphServiceError(CrimeAIError):
    """Graph algorithm failed."""


class RateLimitError(CrimeAIError):
    """Too many requests."""


class StorageError(CrimeAIError):
    """File storage operation failed."""


class ExternalServiceError(CrimeAIError):
    """Third-party service (Supabase, etc.) failed."""
