from __future__ import annotations

"""Feature 39/46 deployment mode runtime.

The module keeps single-instance behavior in process and verifies cluster-core
adapters through real HTTP health and state-sync calls.
"""

import json
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

UTC = timezone.utc
DeploymentMode = Literal["single_prod", "cluster_core"]


class ClusterAdapter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter_id: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    adapter_kind: Literal["http", "grpc"] = "http"
    expected_brain_scope: str = Field(min_length=1)

    @field_validator("base_url")
    @classmethod
    def _strip_base_url(cls, value: str) -> str:
        return value.rstrip("/")


class DeploymentModeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployment_mode: DeploymentMode
    brain_scope: str = Field(min_length=1)
    adapters: list[ClusterAdapter] = Field(default_factory=list)
    state_sync_required: bool = True
    configured_by: str = Field(min_length=1)


class AdapterCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter_id: str
    healthy: bool
    state_sync_ok: bool
    status_code: int
    message: str
    remote_snapshot_version: int | None = None


class DeploymentModeSyncCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_id: str = Field(default_factory=lambda: str(uuid4()))
    deployment_mode: DeploymentMode
    brain_scope: str
    in_process_services: bool
    adapter_results: list[AdapterCheckResult]
    ready: bool
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DeploymentModeState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployment_mode: DeploymentMode
    brain_scope: str
    in_process_services: bool
    adapter_count: int
    last_sync_check: DeploymentModeSyncCheck | None = None
    configured_at: datetime
    configured_by: str


class DeploymentModeRuntime:
    def __init__(self) -> None:
        self._config = DeploymentModeConfig(
            deployment_mode="single_prod",
            brain_scope="zentex.local",
            configured_by="system",
        )
        self._configured_at = datetime.now(UTC)
        self._last_sync_check: DeploymentModeSyncCheck | None = None

    def configure(self, config: DeploymentModeConfig) -> DeploymentModeState:
        if config.deployment_mode == "single_prod" and config.adapters:
            raise ValueError("single_prod must not configure remote cluster adapters")
        if config.deployment_mode == "cluster_core":
            if not config.adapters:
                raise ValueError("cluster_core requires at least one remote adapter")
            unsupported = [item.adapter_id for item in config.adapters if item.adapter_kind != "http"]
            if unsupported:
                raise ValueError(f"unsupported cluster adapter kind for real sync check: {unsupported}")
        self._config = config
        self._configured_at = datetime.now(UTC)
        self._last_sync_check = None
        return self.state()

    def state(self) -> DeploymentModeState:
        return DeploymentModeState(
            deployment_mode=self._config.deployment_mode,
            brain_scope=self._config.brain_scope,
            in_process_services=self._config.deployment_mode == "single_prod",
            adapter_count=len(self._config.adapters),
            last_sync_check=self._last_sync_check,
            configured_at=self._configured_at,
            configured_by=self._config.configured_by,
        )

    def sync_check(self) -> DeploymentModeSyncCheck:
        if self._config.deployment_mode == "single_prod":
            check = DeploymentModeSyncCheck(
                deployment_mode="single_prod",
                brain_scope=self._config.brain_scope,
                in_process_services=True,
                adapter_results=[],
                ready=True,
            )
            self._last_sync_check = check
            return check

        results = [_check_http_adapter(adapter) for adapter in self._config.adapters]
        ready = bool(results) and all(item.healthy and item.state_sync_ok for item in results)
        check = DeploymentModeSyncCheck(
            deployment_mode="cluster_core",
            brain_scope=self._config.brain_scope,
            in_process_services=False,
            adapter_results=results,
            ready=ready,
        )
        self._last_sync_check = check
        return check


def _check_http_adapter(adapter: ClusterAdapter) -> AdapterCheckResult:
    try:
        health = _json_request("GET", f"{adapter.base_url}/health")
        if health.get("status") != "ok":
            return AdapterCheckResult(
                adapter_id=adapter.adapter_id,
                healthy=False,
                state_sync_ok=False,
                status_code=200,
                message="adapter health status is not ok",
            )
        sync = _json_request(
            "POST",
            f"{adapter.base_url}/state-sync/check",
            {"brain_scope": adapter.expected_brain_scope},
        )
        scope_ok = sync.get("brain_scope") == adapter.expected_brain_scope
        version = sync.get("snapshot_version")
        version_ok = isinstance(version, int) and version >= 0
        return AdapterCheckResult(
            adapter_id=adapter.adapter_id,
            healthy=True,
            state_sync_ok=bool(scope_ok and version_ok and sync.get("state_sync_ok") is True),
            status_code=200,
            message="ok" if scope_ok and version_ok and sync.get("state_sync_ok") is True else "state sync contract mismatch",
            remote_snapshot_version=version if isinstance(version, int) else None,
        )
    except HTTPError as exc:
        return AdapterCheckResult(
            adapter_id=adapter.adapter_id,
            healthy=False,
            state_sync_ok=False,
            status_code=exc.code,
            message=str(exc),
        )
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        return AdapterCheckResult(
            adapter_id=adapter.adapter_id,
            healthy=False,
            state_sync_ok=False,
            status_code=0,
            message=str(exc),
        )


def _json_request(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=5) as response:
        raw = response.read().decode("utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("adapter response must be a JSON object")
    return parsed
