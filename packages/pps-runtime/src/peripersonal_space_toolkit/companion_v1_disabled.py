"""V1 safety boundary for the unshipped Android companion experiment."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_COMPANION_HOST = "127.0.0.1"
DEFAULT_COMPANION_PORT = 8767
HEALTH_SCHEMA = "pps-runner-companion-health.v1"
SNAPSHOT_SCHEMA = "pps-runner-companion-snapshot.v1"
DISABLED_REASON = "The Android companion is an unapproved experiment and is not included in PPS Toolkit v1."


class CompanionCommandError(RuntimeError):
    def __init__(self, message: str = DISABLED_REASON, *, status_code: int = 409, reason: str = "companion_not_shipped") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.reason = reason


class MobileRuntimePackageError(CompanionCommandError):
    pass


@dataclass(frozen=True)
class RunnerCompanionConfig:
    host: str = DEFAULT_COMPANION_HOST
    port: int = DEFAULT_COMPANION_PORT
    advertise_ip: str = ""

    @property
    def advertised_host(self) -> str:
        return self.advertise_ip or self.host


class RunnerCompanionService:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def start(self) -> None:
        raise CompanionCommandError()

    def stop(self) -> None:
        return None


def build_pairing_uri(**_kwargs: Any) -> str:
    return ""


def choose_lan_ipv4() -> str:
    return ""


def generate_companion_token() -> str:
    return ""


def pairing_qr_png_bytes(_uri: str) -> bytes:
    raise CompanionCommandError()


def build_mobile_package_list(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {"schema": "pps-mobile-package-list.v1", "packages": [], "disabled": True}


def build_mobile_package_manifest(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    raise MobileRuntimePackageError()


def mobile_asset_path(*_args: Any, **_kwargs: Any) -> Path:
    raise MobileRuntimePackageError()


def mobile_package_id(_package: Any) -> str:
    return ""


def write_mobile_runtime_events(*_args: Any, **_kwargs: Any) -> None:
    raise MobileRuntimePackageError()


def send_android_lsl_command(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    raise CompanionCommandError()
