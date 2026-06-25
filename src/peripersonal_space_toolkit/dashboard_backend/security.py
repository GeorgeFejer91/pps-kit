"""Local companion authorization helpers for the dashboard backend."""

from __future__ import annotations

import hmac
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


TOKEN_HEADER = "X-PPS-Companion-Token"
TOKEN_ENV_VAR = "PPS_DASHBOARD_COMPANION_TOKEN"
REQUIRE_TOKEN_ENV_VAR = "PPS_DASHBOARD_REQUIRE_TOKEN"


def truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "required"}


@dataclass
class CompanionSecurity:
    """Token gate and small capability log for local companion routes."""

    token: str = ""
    require_mutation_token: bool = False
    request_log: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_environment(
        cls,
        *,
        token: str | None = None,
        require_mutation_token: bool | None = None,
    ) -> "CompanionSecurity":
        resolved_token = token if token is not None else os.environ.get(TOKEN_ENV_VAR, "")
        resolved_require = (
            bool(require_mutation_token)
            if require_mutation_token is not None
            else bool(resolved_token) or truthy(os.environ.get(REQUIRE_TOKEN_ENV_VAR))
        )
        if resolved_require and not resolved_token:
            resolved_token = secrets.token_urlsafe(24)
        return cls(token=str(resolved_token or ""), require_mutation_token=resolved_require)

    @property
    def enabled(self) -> bool:
        return self.require_mutation_token and bool(self.token)

    def public_status(self) -> dict[str, Any]:
        return {
            "mutation_token_required": self.enabled,
            "token_header": TOKEN_HEADER,
            "accepted_mutating_requests": sum(1 for item in self.request_log if item.get("accepted")),
            "rejected_mutating_requests": sum(1 for item in self.request_log if not item.get("accepted")),
            "capabilities": [
                "read_state",
                "load_templates",
                "mutate_design",
                "import_audio",
                "bake_stimuli",
                "prepare_session",
                "launch_runner",
                "open_local_folder",
            ],
        }

    def authorize_mutation(
        self,
        *,
        path: str,
        method: str,
        origin: str = "",
        supplied_token: str = "",
    ) -> tuple[bool, str]:
        if not self.enabled:
            self._record(path=path, method=method, origin=origin, accepted=True, reason="token_not_required")
            return True, "token_not_required"
        if supplied_token and hmac.compare_digest(supplied_token, self.token):
            self._record(path=path, method=method, origin=origin, accepted=True, reason="token_accepted")
            return True, "token_accepted"
        reason = "missing_token" if not supplied_token else "stale_or_invalid_token"
        self._record(path=path, method=method, origin=origin, accepted=False, reason=reason)
        return False, reason

    def _record(self, *, path: str, method: str, origin: str, accepted: bool, reason: str) -> None:
        self.request_log.append(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "method": method,
                "path": path,
                "origin": origin,
                "accepted": accepted,
                "reason": reason,
            }
        )
        if len(self.request_log) > 200:
            del self.request_log[:-200]
