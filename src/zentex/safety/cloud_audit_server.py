"""Independent deployable cloud sanity audit server for G30."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from zentex.safety.cloud_auditor import CloudAuditDecision, CloudAuditRequest, CloudDecisionStatus


class CloudAuditServerConfig(BaseModel):
    """Configuration for the standalone cloud audit server."""

    model_config = ConfigDict(extra="forbid")

    api_keys: dict[str, str] = Field(default_factory=dict)
    policy_version: str = "g30-policy-1.0"
    db_path: str = ":memory:"
    replay_window_seconds: int = 300
    deny_action_types: list[str] = Field(default_factory=list)


class CloudAuditDecisionStore:
    """SQLite persistence for cloud audit requests and decisions."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cloud_audit_decisions (
                    request_id TEXT PRIMARY KEY,
                    decision_id TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def save(self, request: CloudAuditRequest, decision: CloudAuditDecision) -> None:
        """Persist one request/decision pair."""

        with self._conn:
            self._conn.execute(
                "INSERT INTO cloud_audit_decisions VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    request.request_id,
                    decision.decision_id,
                    decision.policy_version,
                    decision.status.value,
                    request.model_dump_json(),
                    decision.model_dump_json(),
                    decision.created_at.isoformat(),
                ),
            )

    def get(self, request_id: str) -> dict[str, Any] | None:
        """Return a persisted decision row by request id."""

        row = self._conn.execute(
            "SELECT * FROM cloud_audit_decisions WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        return dict(row) if row else None


class ReplayNonceStore:
    """In-memory replay protection with a fixed timestamp window."""

    def __init__(self, window_seconds: int) -> None:
        self.window_seconds = window_seconds
        self._seen: dict[str, float] = {}

    def check_and_mark(self, request: CloudAuditRequest) -> None:
        """Reject stale or repeated request ids."""

        now = time.time()
        timestamp = request.timestamp.timestamp()
        if abs(now - timestamp) > self.window_seconds:
            raise HTTPException(status_code=401, detail={"error": "stale_request"})
        self._seen = {key: value for key, value in self._seen.items() if now - value <= self.window_seconds}
        if request.request_id in self._seen:
            raise HTTPException(status_code=409, detail={"error": "replay_detected"})
        self._seen[request.request_id] = now


class CloudAuditPolicyEngine:
    """Local JSON-policy-compatible decision engine."""

    def __init__(self, config: CloudAuditServerConfig) -> None:
        self.config = config

    def decide(self, request: CloudAuditRequest) -> tuple[CloudDecisionStatus, str, dict[str, Any]]:
        """Return a conservative policy decision."""

        if request.action_type in set(self.config.deny_action_types):
            return CloudDecisionStatus.REJECTED, "action_type denied by policy", {"policy_rule": "deny_action_type"}
        if request.risk_level == "critical":
            return CloudDecisionStatus.REJECTED, "critical actions require human approval", {"policy_rule": "critical_default_reject"}
        if request.risk_level == "high":
            return CloudDecisionStatus.REVIEW_REQUIRED, "high risk requires external human review", {"policy_rule": "high_review_required"}
        return CloudDecisionStatus.APPROVED, "risk accepted by cloud policy", {"policy_rule": "low_medium_accept"}


def sign_request(request: CloudAuditRequest, secret: str) -> str:
    """Sign the client request canonical string."""

    canonical = f"{request.action_type}|{request.request_id}|{int(request.timestamp.timestamp())}"
    digest = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"hmac-sha256={digest}"


def sign_decision(decision: CloudAuditDecision, secret: str) -> str:
    """Sign the server decision canonical string."""

    canonical = f"{decision.decision_id}|{decision.request_id}|{int(decision.created_at.timestamp())}|{decision.status.value}"
    digest = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"hmac-sha256={digest}"


def create_cloud_audit_app(config: CloudAuditServerConfig) -> FastAPI:
    """Create the standalone FastAPI cloud audit service."""

    app = FastAPI(title="Zentex Cloud Audit Server")
    store = CloudAuditDecisionStore(config.db_path)
    nonce_store = ReplayNonceStore(config.replay_window_seconds)
    policy_engine = CloudAuditPolicyEngine(config)

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {"ok": True, "policy_version": config.policy_version}

    @app.post("/api/v1/sanity")
    def audit(
        payload: CloudAuditRequest,
        x_zentex_api_key: str = Header(default=""),
        x_zentex_signature: str = Header(default=""),
    ) -> CloudAuditDecision:
        secret = config.api_keys.get(x_zentex_api_key)
        if not secret:
            raise HTTPException(status_code=401, detail={"error": "invalid_api_key"})
        expected_signature = sign_request(payload, secret)
        if not hmac.compare_digest(expected_signature, x_zentex_signature):
            raise HTTPException(status_code=401, detail={"error": "invalid_signature"})
        nonce_store.check_and_mark(payload)
        status, reason, constraints = policy_engine.decide(payload)
        decision = CloudAuditDecision(
            decision_id=f"g30-{uuid4().hex[:12]}",
            request_id=payload.request_id,
            policy_version=config.policy_version,
            status=status,
            reason=reason,
            constraints=constraints,
            created_at=datetime.now(timezone.utc),
        )
        decision.signature = sign_decision(decision, secret)
        store.save(payload, decision)
        return decision

    @app.get("/api/v1/sanity/{request_id}")
    def get_decision(request_id: str) -> dict[str, Any]:
        row = store.get(request_id)
        if row is None:
            raise HTTPException(status_code=404, detail={"error": "request_not_found"})
        return row

    return app
