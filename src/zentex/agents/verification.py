from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field


UTC = timezone.utc


class AgentVerificationMethod(str, Enum):
    """Supported Zentex-local verification methods for external capabilities."""

    REMOTE_RESULT_VIEW = "remote_result_view"
    ACTIVE_PROBE = "active_probe"
    RULE_ANALYSIS = "rule_analysis"
    LLM_ANALYSIS = "llm_analysis"


class AgentVerificationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    UNCERTAIN = "uncertain"
    SKIPPED = "skipped"


class AgentEvidenceBundle(BaseModel):
    """Local evidence collected around an external Agent/MCP/CLI invocation."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    invocation_id: str = Field(default_factory=lambda: f"agent-invocation-{uuid4().hex[:12]}")
    capability: str | None = None
    request_payload: dict[str, Any] = Field(default_factory=dict)
    normalized_result: Any = None
    raw_response: Any = None
    observation_evidence: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RemoteResultViewConfig(BaseModel):
    """Optional remote result-view interface implemented by an external Agent."""

    model_config = ConfigDict(extra="forbid")

    url: str
    method: Literal["GET", "POST"] = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    body: dict[str, Any] | None = None
    expected_status: int = 200
    expected_json_path: str | None = None
    expected_equals: Any = None
    expected_contains: str | None = None


class ActiveProbeConfig(BaseModel):
    """Optional active probe used to verify externally observable effects."""

    model_config = ConfigDict(extra="forbid")

    name: str
    url: str
    method: Literal["GET", "POST"] = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    body: dict[str, Any] | None = None
    expected_status: int = 200
    expected_json_path: str | None = None
    expected_equals: Any = None
    expected_contains: str | None = None


class RuleAnalysisConfig(BaseModel):
    """Structured local rules applied to the evidence bundle."""

    model_config = ConfigDict(extra="forbid")

    required_paths: list[str] = Field(default_factory=list)
    non_empty_paths: list[str] = Field(default_factory=list)
    equals: dict[str, Any] = Field(default_factory=dict)
    contains: dict[str, str] = Field(default_factory=dict)


class LlmAnalysisConfig(BaseModel):
    """Optional LLM verifier configuration.

    The provider is deliberately not embedded here. Callers inject an analyzer
    callable so this module stays independent from any LLM runtime.
    """

    model_config = ConfigDict(extra="forbid")

    prompt: str
    pass_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    required: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentVerificationPlan(BaseModel):
    """Local verification plan for one invocation."""

    model_config = ConfigDict(extra="forbid")

    methods: list[AgentVerificationMethod] = Field(default_factory=list)
    remote_result_view: RemoteResultViewConfig | None = None
    active_probes: list[ActiveProbeConfig] = Field(default_factory=list)
    rule_analysis: RuleAnalysisConfig | None = None
    llm_analysis: LlmAnalysisConfig | None = None


class AgentVerificationCheck(BaseModel):
    """Result of a single verifier."""

    model_config = ConfigDict(extra="forbid")

    method: AgentVerificationMethod
    status: AgentVerificationStatus
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    message: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class AgentVerificationResult(BaseModel):
    """Aggregated verification result for an invocation."""

    model_config = ConfigDict(extra="forbid")

    overall_status: AgentVerificationStatus
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    checks: list[AgentVerificationCheck] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


AgentLlmAnalyzer = Callable[
    [AgentEvidenceBundle, LlmAnalysisConfig],
    AgentVerificationCheck | dict[str, Any] | Awaitable[AgentVerificationCheck | dict[str, Any]],
]


class AgentVerificationService:
    """Zentex-local verifier for external capability execution evidence."""

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        llm_analyzer: AgentLlmAnalyzer | None = None,
    ) -> None:
        self.timeout = httpx.Timeout(timeout)
        self.llm_analyzer = llm_analyzer

    async def verify(
        self,
        evidence: AgentEvidenceBundle,
        plan: AgentVerificationPlan | None,
    ) -> AgentVerificationResult:
        if plan is None or not plan.methods:
            return AgentVerificationResult(
                overall_status=AgentVerificationStatus.SKIPPED,
                confidence=0.0,
                checks=[],
            )

        working_evidence = evidence.model_copy(deep=True)
        checks: list[AgentVerificationCheck] = []
        for method in plan.methods:
            if method == AgentVerificationMethod.REMOTE_RESULT_VIEW:
                checks.append(await self._verify_remote_result_view(working_evidence, plan.remote_result_view))
            elif method == AgentVerificationMethod.ACTIVE_PROBE:
                checks.extend(await self._verify_active_probes(working_evidence, plan.active_probes))
            elif method == AgentVerificationMethod.RULE_ANALYSIS:
                checks.append(self._verify_rules(working_evidence, plan.rule_analysis))
            elif method == AgentVerificationMethod.LLM_ANALYSIS:
                checks.append(await self._verify_with_llm(working_evidence, plan.llm_analysis))
        return self._aggregate(checks)

    async def _verify_remote_result_view(
        self,
        evidence: AgentEvidenceBundle,
        config: RemoteResultViewConfig | None,
    ) -> AgentVerificationCheck:
        method = AgentVerificationMethod.REMOTE_RESULT_VIEW
        if config is None:
            return self._skipped(method, "remote result-view interface is not configured")
        check = await self._fetch_and_match(method, config, evidence)
        if check.status == AgentVerificationStatus.PASSED:
            evidence.observation_evidence["remote_result_view"] = check.evidence.get("response")
        return check

    async def _verify_active_probes(
        self,
        evidence: AgentEvidenceBundle,
        configs: list[ActiveProbeConfig],
    ) -> list[AgentVerificationCheck]:
        method = AgentVerificationMethod.ACTIVE_PROBE
        if not configs:
            return [self._skipped(method, "active probes are not configured")]

        checks: list[AgentVerificationCheck] = []
        probe_evidence: dict[str, Any] = {}
        for config in configs:
            check = await self._fetch_and_match(method, config, evidence, evidence_name=config.name)
            checks.append(check)
            if check.status == AgentVerificationStatus.PASSED:
                probe_evidence[config.name] = check.evidence.get("response")
        if probe_evidence:
            evidence.observation_evidence.setdefault("active_probes", {}).update(probe_evidence)
        return checks

    def _verify_rules(
        self,
        evidence: AgentEvidenceBundle,
        config: RuleAnalysisConfig | None,
    ) -> AgentVerificationCheck:
        method = AgentVerificationMethod.RULE_ANALYSIS
        if config is None:
            return self._skipped(method, "rule analysis is not configured")

        root = evidence.model_dump(mode="json")
        failures: list[str] = []
        details: dict[str, Any] = {}

        for path in config.required_paths:
            found, value = self._lookup_path(root, path)
            details[path] = value if found else None
            if not found:
                failures.append(f"missing required path: {path}")

        for path in config.non_empty_paths:
            found, value = self._lookup_path(root, path)
            details[path] = value if found else None
            if not found or value in (None, "", [], {}):
                failures.append(f"empty required path: {path}")

        for path, expected in config.equals.items():
            found, value = self._lookup_path(root, path)
            details[path] = value if found else None
            if not found or value != expected:
                failures.append(f"path {path} expected {expected!r}, got {value!r}")

        for path, expected_text in config.contains.items():
            found, value = self._lookup_path(root, path)
            details[path] = value if found else None
            if not found or expected_text not in str(value):
                failures.append(f"path {path} does not contain {expected_text!r}")

        if failures:
            return AgentVerificationCheck(
                method=method,
                status=AgentVerificationStatus.FAILED,
                confidence=1.0,
                message="; ".join(failures),
                evidence={"checked_paths": details, "failures": failures},
            )
        return AgentVerificationCheck(
            method=method,
            status=AgentVerificationStatus.PASSED,
            confidence=1.0,
            message="rule analysis passed",
            evidence={"checked_paths": details},
        )

    async def _verify_with_llm(
        self,
        evidence: AgentEvidenceBundle,
        config: LlmAnalysisConfig | None,
    ) -> AgentVerificationCheck:
        method = AgentVerificationMethod.LLM_ANALYSIS
        if config is None:
            return self._skipped(method, "LLM analysis is not configured")
        if self.llm_analyzer is None:
            status = AgentVerificationStatus.UNCERTAIN if config.required else AgentVerificationStatus.SKIPPED
            return AgentVerificationCheck(
                method=method,
                status=status,
                confidence=0.0,
                message="LLM analyzer is not attached",
                evidence={"required": config.required},
            )

        result = self.llm_analyzer(evidence, config)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, AgentVerificationCheck):
            return result

        payload = dict(result)
        payload.setdefault("method", method)
        if "status" not in payload:
            score = float(payload.get("confidence") or payload.get("score") or 0.0)
            payload["status"] = (
                AgentVerificationStatus.PASSED
                if score >= config.pass_threshold
                else AgentVerificationStatus.UNCERTAIN
            )
        payload.setdefault("confidence", float(payload.get("score") or 0.0))
        payload.setdefault("message", "LLM analysis completed")
        payload.setdefault("evidence", {})
        return AgentVerificationCheck.model_validate(payload)

    async def _fetch_and_match(
        self,
        method: AgentVerificationMethod,
        config: RemoteResultViewConfig | ActiveProbeConfig,
        evidence: AgentEvidenceBundle,
        *,
        evidence_name: str | None = None,
    ) -> AgentVerificationCheck:
        try:
            response = await self._request_json(config, evidence)
        except Exception as exc:
            return AgentVerificationCheck(
                method=method,
                status=AgentVerificationStatus.UNCERTAIN,
                confidence=0.0,
                message=f"verification request failed: {exc}",
                evidence={"name": evidence_name, "url": config.url},
            )

        status_code = int(response["status_code"])
        payload = response["json"]
        if status_code != config.expected_status:
            return AgentVerificationCheck(
                method=method,
                status=AgentVerificationStatus.FAILED,
                confidence=1.0,
                message=f"expected HTTP {config.expected_status}, got {status_code}",
                evidence={"name": evidence_name, "response": payload, "status_code": status_code},
            )

        if config.expected_json_path:
            found, value = self._lookup_path(payload, config.expected_json_path)
            if not found:
                return AgentVerificationCheck(
                    method=method,
                    status=AgentVerificationStatus.FAILED,
                    confidence=1.0,
                    message=f"missing expected JSON path: {config.expected_json_path}",
                    evidence={"name": evidence_name, "response": payload, "status_code": status_code},
                )
            if config.expected_equals is not None and value != config.expected_equals:
                return AgentVerificationCheck(
                    method=method,
                    status=AgentVerificationStatus.FAILED,
                    confidence=1.0,
                    message=f"expected {config.expected_json_path}={config.expected_equals!r}, got {value!r}",
                    evidence={"name": evidence_name, "response": payload, "status_code": status_code},
                )
            if config.expected_contains is not None and config.expected_contains not in str(value):
                return AgentVerificationCheck(
                    method=method,
                    status=AgentVerificationStatus.FAILED,
                    confidence=1.0,
                    message=f"{config.expected_json_path} does not contain {config.expected_contains!r}",
                    evidence={"name": evidence_name, "response": payload, "status_code": status_code},
                )

        return AgentVerificationCheck(
            method=method,
            status=AgentVerificationStatus.PASSED,
            confidence=0.8,
            message="verification request matched expected response",
            evidence={"name": evidence_name, "response": payload, "status_code": status_code},
        )

    async def _request_json(
        self,
        config: RemoteResultViewConfig | ActiveProbeConfig,
        evidence: AgentEvidenceBundle,
    ) -> dict[str, Any]:
        url = self._format_value(config.url, evidence)
        headers = {key: self._format_value(value, evidence) for key, value in config.headers.items()}
        body = self._format_body(config.body, evidence) if config.body is not None else None
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(config.method, url, headers=headers, json=body)
        response_json = response.json() if response.content else {}
        if not isinstance(response_json, dict):
            response_json = {"value": response_json}
        return {"status_code": response.status_code, "json": response_json}

    @staticmethod
    def _format_value(value: str, evidence: AgentEvidenceBundle) -> str:
        values = evidence.model_dump(mode="json")
        try:
            return value.format(**values)
        except (KeyError, IndexError, AttributeError):
            return value

    @classmethod
    def _format_body(cls, body: Any, evidence: AgentEvidenceBundle) -> Any:
        if isinstance(body, str):
            return cls._format_value(body, evidence)
        if isinstance(body, list):
            return [cls._format_body(item, evidence) for item in body]
        if isinstance(body, dict):
            return {key: cls._format_body(value, evidence) for key, value in body.items()}
        return body

    @staticmethod
    def _lookup_path(root: Any, path: str) -> tuple[bool, Any]:
        current = root
        clean_path = path[2:] if path.startswith("$.") else path
        if not clean_path:
            return True, current
        for part in clean_path.split("."):
            if isinstance(current, dict):
                if part not in current:
                    return False, None
                current = current[part]
            elif isinstance(current, list) and part.isdigit():
                index = int(part)
                if index >= len(current):
                    return False, None
                current = current[index]
            else:
                return False, None
        return True, current

    @staticmethod
    def _skipped(method: AgentVerificationMethod, message: str) -> AgentVerificationCheck:
        return AgentVerificationCheck(
            method=method,
            status=AgentVerificationStatus.SKIPPED,
            confidence=0.0,
            message=message,
        )

    @staticmethod
    def _aggregate(checks: list[AgentVerificationCheck]) -> AgentVerificationResult:
        if not checks:
            return AgentVerificationResult(overall_status=AgentVerificationStatus.SKIPPED, confidence=0.0)

        statuses = [check.status for check in checks]
        if AgentVerificationStatus.FAILED in statuses:
            overall = AgentVerificationStatus.FAILED
        elif AgentVerificationStatus.UNCERTAIN in statuses:
            overall = AgentVerificationStatus.UNCERTAIN
        elif AgentVerificationStatus.PASSED in statuses:
            overall = AgentVerificationStatus.PASSED
        else:
            overall = AgentVerificationStatus.SKIPPED

        scored = [check.confidence for check in checks if check.status != AgentVerificationStatus.SKIPPED]
        confidence = sum(scored) / len(scored) if scored else 0.0
        return AgentVerificationResult(
            overall_status=overall,
            confidence=round(confidence, 4),
            checks=checks,
        )
