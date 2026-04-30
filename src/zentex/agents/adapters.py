from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, field, replace
from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field

from zentex.agents.auth import AgentAuthError, AgentResolvedAuth, redact_sensitive
from zentex.agents.bridge import AgentBridge, AgentBridgeError
from zentex.agents.manager import AgentAsset
from zentex.foundation.contracts.service_response import ServiceErrorCode


AgentAdapterType = Literal["legacy_bridge", "http_json", "cli", "mcp", "webhook"]

_TEMPLATE_PATTERN = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)")


class AgentAdapterError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: ServiceErrorCode = ServiceErrorCode.INTERNAL_UNRECOVERABLE,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class AgentInvocationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invocation_id: str
    external_task_ref: str
    agent_id: str
    status: Literal["started", "running", "completed", "failed", "submitted", "uncertain", "waiting_external_human_review"]
    zentex_task_id: str | None = None
    callback_url: str | None = None
    normalized_result: Any = None
    raw_response: Any = None
    adapter_metadata: dict[str, Any] = Field(default_factory=dict)
    elapsed_ms: int = 0


@dataclass(frozen=True)
class AgentInvocationContext:
    invocation_id: str
    external_task_ref: str
    zentex_task_id: str | None = None
    callback_url: str | None = None
    callback_token: str | None = None
    auth: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentInvocationDependencies:
    cli_service: Any = None
    mcp_service: Any = None
    auth_service: Any = None


class AgentInvocationAdapter:
    def __init__(self, *, bridge: AgentBridge, timeout: float = 30.0) -> None:
        self.bridge = bridge
        self.timeout = httpx.Timeout(timeout)

    async def invoke(
        self,
        asset: AgentAsset,
        payload: dict[str, Any],
        *,
        invocation_id: str | None = None,
        external_task_ref: str | None = None,
        zentex_task_id: str | None = None,
        callback_url: str | None = None,
        callback_token: str | None = None,
        dependencies: AgentInvocationDependencies | None = None,
    ) -> AgentInvocationResult:
        invocation_id = invocation_id or f"agent-invocation-{uuid4().hex[:12]}"
        external_task_ref = external_task_ref or f"ztx_taskref_{uuid4().hex[:18]}"
        context = AgentInvocationContext(
            invocation_id=invocation_id,
            external_task_ref=external_task_ref,
            zentex_task_id=zentex_task_id,
            callback_url=callback_url,
            callback_token=callback_token,
        )
        adapter_type = str(getattr(asset, "adapter_type", "legacy_bridge") or "legacy_bridge")
        started_at = perf_counter()
        try:
            if adapter_type == "legacy_bridge":
                return await self._invoke_legacy_bridge(asset, payload, context=context, started_at=started_at, dependencies=dependencies)
            if adapter_type == "http_json":
                return await self._invoke_http_json(asset, payload, context=context, started_at=started_at, dependencies=dependencies)
            if adapter_type == "webhook":
                return await self._invoke_webhook(asset, payload, context=context, started_at=started_at, dependencies=dependencies)
            if adapter_type == "cli":
                return self._invoke_cli(asset, payload, context=context, started_at=started_at, dependencies=dependencies)
            if adapter_type == "mcp":
                return self._invoke_mcp(asset, payload, context=context, started_at=started_at, dependencies=dependencies)
        except AgentAdapterError:
            raise
        except AgentAuthError:
            raise
        except AgentBridgeError as exc:
            raise AgentAdapterError(str(exc), code=self._bridge_code(exc), status_code=exc.status_code) from exc
        except httpx.HTTPStatusError as exc:
            raise AgentAdapterError(
                f"Agent adapter HTTP error: {exc}",
                code=self._http_code(exc.response.status_code),
                status_code=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise AgentAdapterError(
                f"Agent adapter transport failure: {exc}",
                code=ServiceErrorCode.DEPENDENCY_UNAVAILABLE,
            ) from exc
        except Exception as exc:
            raise AgentAdapterError(f"Agent adapter failed: {exc}") from exc
        raise AgentAdapterError(
            f"Unsupported agent adapter_type: {adapter_type}",
            code=ServiceErrorCode.INVALID_ARGUMENT,
        )

    async def check_health(self, asset: AgentAsset, *, dependencies: AgentInvocationDependencies | None = None) -> bool:
        adapter_type = str(getattr(asset, "adapter_type", "legacy_bridge") or "legacy_bridge")
        config = dict(getattr(asset, "adapter_config", {}) or {})
        health_config = config.get("health_probe")
        if adapter_type == "legacy_bridge":
            return await self.bridge.check_health(asset)
        if adapter_type in {"http_json", "webhook"}:
            if not isinstance(health_config, dict):
                return False
            try:
                context = AgentInvocationContext(invocation_id="health-probe", external_task_ref="health-probe")
                url = self._http_url(asset, health_config, self._root(asset, {}, {}, context))
                method = str(health_config.get("method") or "GET").upper()
                headers = self._render(health_config.get("headers", {}), self._root(asset, {}, {}, context))
                body = self._render(health_config.get("body_template"), self._root(asset, {}, {}, context))
                expected_status = int(health_config.get("expected_status", 200))
                async with httpx.AsyncClient(timeout=float(health_config.get("timeout", 5.0))) as client:
                    response = await client.request(method, url, headers=headers, json=body)
                return response.status_code == expected_status
            except Exception:
                return False
        if adapter_type == "cli" and dependencies and dependencies.cli_service:
            try:
                health = dependencies.cli_service.get_tool_health(str(config.get("tool_name")))
                return bool(health.get("healthy", health.get("status") in {"active", "ok"}))
            except Exception:
                return False
        if adapter_type == "mcp" and dependencies and dependencies.mcp_service:
            try:
                health = dependencies.mcp_service.get_server_health(str(config.get("server_id")))
                return str(health.get("status") or "").lower() in {"online", "healthy", "ok"}
            except Exception:
                return False
        return False

    async def _invoke_legacy_bridge(
        self,
        asset: AgentAsset,
        payload: dict[str, Any],
        *,
        context: AgentInvocationContext,
        started_at: float,
        dependencies: AgentInvocationDependencies | None,
    ) -> AgentInvocationResult:
        auth = await self._resolve_auth(asset, dependencies=dependencies)
        auth_context = replace(context, auth=auth.auth_data)
        try:
            raw = await self._execute_legacy_bridge(asset, self._default_external_payload(payload, auth_context), auth.headers)
        except AgentBridgeError as exc:
            if exc.status_code in {401, 403} and auth.refreshable:
                refreshed = await self._resolve_auth(asset, dependencies=dependencies, force_refresh=True)
                auth_context = replace(context, auth=refreshed.auth_data)
                raw = await self._execute_legacy_bridge(
                    asset,
                    self._default_external_payload(payload, auth_context),
                    refreshed.headers,
                )
            else:
                raise
        return AgentInvocationResult(
            invocation_id=context.invocation_id,
            external_task_ref=context.external_task_ref,
            agent_id=asset.agent_id,
            status="completed",
            zentex_task_id=context.zentex_task_id,
            callback_url=context.callback_url,
            normalized_result=raw,
            raw_response=raw,
            adapter_metadata=redact_sensitive({"adapter_type": "legacy_bridge", "endpoint": asset.endpoint, **auth.metadata}),
            elapsed_ms=self._elapsed_ms(started_at),
        )

    async def _execute_legacy_bridge(
        self,
        asset: AgentAsset,
        payload: dict[str, Any],
        auth_headers: dict[str, str],
    ) -> dict[str, Any]:
        signature = inspect.signature(self.bridge.execute_task)
        if "auth_headers" in signature.parameters:
            return await self.bridge.execute_task(asset, payload, auth_headers=auth_headers)
        return await self.bridge.execute_task(asset, payload)

    async def _invoke_http_json(
        self,
        asset: AgentAsset,
        payload: dict[str, Any],
        *,
        context: AgentInvocationContext,
        started_at: float,
        dependencies: AgentInvocationDependencies | None,
    ) -> AgentInvocationResult:
        return await self._invoke_http_like(
            asset,
            payload,
            context=context,
            started_at=started_at,
            adapter_type="http_json",
            default_status="completed",
            dependencies=dependencies,
        )

    async def _invoke_webhook(
        self,
        asset: AgentAsset,
        payload: dict[str, Any],
        *,
        context: AgentInvocationContext,
        started_at: float,
        dependencies: AgentInvocationDependencies | None,
    ) -> AgentInvocationResult:
        return await self._invoke_http_like(
            asset,
            payload,
            context=context,
            started_at=started_at,
            adapter_type="webhook",
            default_status="submitted",
            dependencies=dependencies,
        )

    async def _invoke_http_like(
        self,
        asset: AgentAsset,
        payload: dict[str, Any],
        *,
        context: AgentInvocationContext,
        started_at: float,
        adapter_type: str,
        default_status: Literal["completed", "submitted"],
        dependencies: AgentInvocationDependencies | None,
    ) -> AgentInvocationResult:
        config = dict(getattr(asset, "adapter_config", {}) or {})
        auth = await self._resolve_auth(asset, dependencies=dependencies)
        auth_context = replace(context, auth=auth.auth_data)
        root = self._root(asset, payload, {}, auth_context)
        url = self._http_url(asset, config, root)
        method = str(config.get("method") or "POST").upper()
        headers = {
            **self._render(config.get("headers", {}), root),
            **auth.headers,
        }
        params = {
            **self._render(config.get("query", config.get("params", {})), root),
            **auth.query,
        }
        if "body_template" in config:
            body = self._render(config.get("body_template"), root)
        else:
            body = self._default_external_payload(payload, auth_context)
        if auth.body_fields and isinstance(body, dict):
            body = {**body, **auth.body_fields}
        expected_status = int(config.get("expected_status", 200))
        timeout = float(config.get("timeout", 30.0))

        async with httpx.AsyncClient(timeout=timeout) as client:
            request_kwargs = {"headers": headers, "params": params, "json": body}
            if auth.cookies:
                request_kwargs["cookies"] = auth.cookies
            response = await client.request(method, url, **request_kwargs)
            if response.status_code in {401, 403} and auth.refreshable:
                refreshed = await self._resolve_auth(asset, dependencies=dependencies, force_refresh=True)
                auth_context = replace(context, auth=refreshed.auth_data)
                root = self._root(asset, payload, {}, auth_context)
                headers = {
                    **self._render(config.get("headers", {}), root),
                    **refreshed.headers,
                }
                params = {
                    **self._render(config.get("query", config.get("params", {})), root),
                    **refreshed.query,
                }
                if "body_template" in config:
                    body = self._render(config.get("body_template"), root)
                else:
                    body = self._default_external_payload(payload, auth_context)
                if refreshed.body_fields and isinstance(body, dict):
                    body = {**body, **refreshed.body_fields}
                auth = refreshed
                request_kwargs = {"headers": headers, "params": params, "json": body}
                if auth.cookies:
                    request_kwargs["cookies"] = auth.cookies
                response = await client.request(method, url, **request_kwargs)
        raw = self._response_payload(response)
        if response.status_code != expected_status:
            raise AgentAdapterError(
                f"{adapter_type} expected HTTP {expected_status}, got {response.status_code}",
                code=self._http_code(response.status_code),
                status_code=response.status_code,
            )
        normalized = self._mapped_response(asset, payload, auth_context, raw, config)
        return AgentInvocationResult(
            invocation_id=context.invocation_id,
            external_task_ref=context.external_task_ref,
            agent_id=asset.agent_id,
            status=default_status,
            zentex_task_id=context.zentex_task_id,
            callback_url=context.callback_url,
            normalized_result=normalized,
            raw_response=raw,
            adapter_metadata={
                "adapter_type": adapter_type,
                "endpoint": asset.endpoint,
                "url": url,
                "method": method,
                "http_status": response.status_code,
                **auth.metadata,
            },
            elapsed_ms=self._elapsed_ms(started_at),
        )

    def _invoke_cli(
        self,
        asset: AgentAsset,
        payload: dict[str, Any],
        *,
        context: AgentInvocationContext,
        started_at: float,
        dependencies: AgentInvocationDependencies | None,
    ) -> AgentInvocationResult:
        if dependencies is None or dependencies.cli_service is None:
            raise AgentAdapterError("CLI adapter requires CliIntegrationService", code=ServiceErrorCode.DEPENDENCY_UNAVAILABLE)
        config = dict(getattr(asset, "adapter_config", {}) or {})
        root = self._root(asset, payload, {}, context)
        tool_name = str(self._render(config.get("tool_name"), root) or "").strip()
        if not tool_name:
            raise AgentAdapterError("CLI adapter requires adapter_config.tool_name", code=ServiceErrorCode.INVALID_ARGUMENT)
        response = dependencies.cli_service.test_call(
            tool_name,
            arguments=self._render(config.get("arguments", []), root),
            stdin_input=self._render(config.get("stdin_input"), root),
            working_directory=self._render(config.get("working_directory"), root),
            timeout_seconds=float(config.get("timeout_seconds", 15.0)),
        )
        raw = self._dump(response.data)
        normalized = self._mapped_response(asset, payload, context, raw, config)
        return AgentInvocationResult(
            invocation_id=context.invocation_id,
            external_task_ref=context.external_task_ref,
            agent_id=asset.agent_id,
            status="completed" if getattr(response, "is_ok", False) else "failed",
            zentex_task_id=context.zentex_task_id,
            callback_url=context.callback_url,
            normalized_result=normalized,
            raw_response=raw,
            adapter_metadata={"adapter_type": "cli", "tool_name": tool_name, "service_status": str(response.status)},
            elapsed_ms=self._elapsed_ms(started_at),
        )

    def _invoke_mcp(
        self,
        asset: AgentAsset,
        payload: dict[str, Any],
        *,
        context: AgentInvocationContext,
        started_at: float,
        dependencies: AgentInvocationDependencies | None,
    ) -> AgentInvocationResult:
        if dependencies is None or dependencies.mcp_service is None:
            raise AgentAdapterError("MCP adapter requires McpIntegrationService", code=ServiceErrorCode.DEPENDENCY_UNAVAILABLE)
        config = dict(getattr(asset, "adapter_config", {}) or {})
        root = self._root(asset, payload, {}, context)
        server_id = str(self._render(config.get("server_id"), root) or "").strip()
        tool_name = str(self._render(config.get("tool_name"), root) or "").strip()
        if not server_id or not tool_name:
            raise AgentAdapterError("MCP adapter requires server_id and tool_name", code=ServiceErrorCode.INVALID_ARGUMENT)
        raw = dependencies.mcp_service.test_call(
            server_id,
            tool_name=tool_name,
            arguments=self._render(config.get("arguments", {}), root),
            trace_id=context.invocation_id,
        )
        status_text = str(raw.get("status") or "").lower() if isinstance(raw, dict) else ""
        normalized = self._mapped_response(asset, payload, context, raw, config)
        return AgentInvocationResult(
            invocation_id=context.invocation_id,
            external_task_ref=context.external_task_ref,
            agent_id=asset.agent_id,
            status="completed" if status_text in {"completed", "success", "ok"} else "failed",
            zentex_task_id=context.zentex_task_id,
            callback_url=context.callback_url,
            normalized_result=normalized,
            raw_response=raw,
            adapter_metadata={"adapter_type": "mcp", "server_id": server_id, "tool_name": tool_name},
            elapsed_ms=self._elapsed_ms(started_at),
        )

    def _mapped_response(
        self,
        asset: AgentAsset,
        payload: dict[str, Any],
        context: AgentInvocationContext,
        raw: Any,
        config: dict[str, Any],
    ) -> Any:
        response_mapping = config.get("response_mapping")
        if response_mapping is None:
            return raw
        return self._render(response_mapping, self._root(asset, payload, raw, context))

    async def _resolve_auth(
        self,
        asset: AgentAsset,
        *,
        dependencies: AgentInvocationDependencies | None,
        force_refresh: bool = False,
    ) -> AgentResolvedAuth:
        if dependencies is None or dependencies.auth_service is None:
            legacy_token = getattr(asset, "auth_token", None)
            if legacy_token:
                return AgentResolvedAuth(
                    auth_data={"access_token": legacy_token, "token": legacy_token},
                    headers={"Authorization": f"Bearer {legacy_token}"},
                    metadata={"auth_type": "legacy_auth_token"},
                )
            if dict(getattr(asset, "auth_config", {}) or {}).get("type") not in {None, "", "none"}:
                raise AgentAuthError(
                    "Agent auth_config requires AgentAuthService",
                    code=ServiceErrorCode.DEPENDENCY_UNAVAILABLE,
                )
            return AgentResolvedAuth()
        return await dependencies.auth_service.resolve(asset, force_refresh=force_refresh)

    @staticmethod
    def _response_payload(response: httpx.Response) -> Any:
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {"text": response.text}

    @staticmethod
    def _dump(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        return value

    @classmethod
    def _render(cls, value: Any, root: dict[str, Any]) -> Any:
        if isinstance(value, str):
            match = _TEMPLATE_PATTERN.fullmatch(value)
            if match:
                return cls._lookup(root, match.group(1))

            def replace(match_obj: re.Match[str]) -> str:
                return str(cls._lookup(root, match_obj.group(1)))

            return _TEMPLATE_PATTERN.sub(replace, value)
        if isinstance(value, list):
            return [cls._render(item, root) for item in value]
        if isinstance(value, dict):
            return {key: cls._render(item, root) for key, item in value.items()}
        return value

    @classmethod
    def _lookup(cls, root: Any, path: str) -> Any:
        current = root
        for part in path.split("."):
            if isinstance(current, dict):
                if part not in current:
                    raise AgentAdapterError(f"Template path not found: ${path}", code=ServiceErrorCode.INVALID_ARGUMENT)
                current = current[part]
            elif isinstance(current, list) and part.isdigit():
                index = int(part)
                if index >= len(current):
                    raise AgentAdapterError(f"Template path not found: ${path}", code=ServiceErrorCode.INVALID_ARGUMENT)
                current = current[index]
            else:
                raise AgentAdapterError(f"Template path not found: ${path}", code=ServiceErrorCode.INVALID_ARGUMENT)
        return current

    @staticmethod
    def _root(asset: AgentAsset, payload: dict[str, Any], response: Any, context: AgentInvocationContext) -> dict[str, Any]:
        agent_data = asset.model_dump(mode="json")
        agent_data["auth_token"] = getattr(asset, "auth_token", None)
        return {
            "payload": payload,
            "agent": agent_data,
            "response": response,
            "auth": context.auth,
            "invocation": {
                "id": context.invocation_id,
                "agent_id": asset.agent_id,
                "external_task_ref": context.external_task_ref,
                "task_ref": context.external_task_ref,
                "zentex_task_id": context.zentex_task_id,
                "callback_url": context.callback_url,
                "callback_token": context.callback_token,
            },
        }

    @staticmethod
    def _default_external_payload(payload: dict[str, Any], context: AgentInvocationContext) -> dict[str, Any]:
        enriched = dict(payload)
        enriched.setdefault("external_task_ref", context.external_task_ref)
        enriched.setdefault("task_ref", context.external_task_ref)
        if context.zentex_task_id:
            enriched.setdefault("zentex_task_id", context.zentex_task_id)
        if context.callback_url:
            enriched.setdefault("callback_url", context.callback_url)
        if context.callback_token:
            enriched.setdefault("callback_token", context.callback_token)
        return enriched

    @classmethod
    def _http_url(cls, asset: AgentAsset, config: dict[str, Any], root: dict[str, Any]) -> str:
        if config.get("url"):
            return str(cls._render(config["url"], root))
        path = str(cls._render(config.get("path", ""), root) or "")
        if path:
            return asset.endpoint.rstrip("/") + "/" + path.lstrip("/")
        return asset.endpoint

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return max(0, int((perf_counter() - started_at) * 1000))

    @staticmethod
    def _http_code(status_code: int) -> ServiceErrorCode:
        if status_code in {401, 403}:
            return ServiceErrorCode.PERMISSION_DENIED
        if status_code == 404:
            return ServiceErrorCode.NOT_FOUND
        if status_code == 400:
            return ServiceErrorCode.INVALID_ARGUMENT
        if status_code >= 500:
            return ServiceErrorCode.DEPENDENCY_UNAVAILABLE
        return ServiceErrorCode.INTERNAL_UNRECOVERABLE

    @classmethod
    def _bridge_code(cls, exc: AgentBridgeError) -> ServiceErrorCode:
        if exc.status_code:
            return cls._http_code(exc.status_code)
        if "transport failure" in str(exc).lower() or "timeout" in str(exc).lower():
            return ServiceErrorCode.DEPENDENCY_UNAVAILABLE
        return ServiceErrorCode.INTERNAL_UNRECOVERABLE
