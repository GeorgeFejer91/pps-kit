"""Stable, language-neutral contracts for the Designer application boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


APPLICATION_ERROR_SCHEMA = "pps-application-error.v1"


@dataclass(frozen=True)
class ApplicationError:
    """A safe error payload that can cross REST, IPC, or test adapters."""

    code: str
    message: str
    retryable: bool = False
    segment_key: str = ""
    schema: str = APPLICATION_ERROR_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": self.schema,
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.segment_key:
            payload["segment_key"] = self.segment_key
        return payload


def application_error_from_exception(
    exc: Exception,
    *,
    code: str = "request_failed",
    fallback_message: str = "The requested operation failed. Review the local log for details.",
) -> ApplicationError:
    """Convert a domain exception without leaking unexpected implementation details."""

    safe_types = (ValueError, RuntimeError, FileNotFoundError, KeyError)
    message = str(exc).strip() if isinstance(exc, safe_types) else fallback_message
    return ApplicationError(
        code=str(getattr(exc, "code", "") or code),
        message=message or fallback_message,
        retryable=bool(getattr(exc, "retryable", False)),
        segment_key=str(getattr(exc, "segment_key", "") or ""),
    )
