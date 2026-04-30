from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field

from zentex.common.database import DatabaseConnection
from zentex.common.storage_paths import get_storage_paths
from zentex.foundation.contracts.service_response import ServiceErrorCode


UTC = timezone.utc
_SENSITIVE_KEY_TOKENS = {
    "authorization",
    "cookie",
    "set-cookie",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "callback_token",
    "client_secret",
    "password",
    "secret",
    "token",
}


class AgentAuthError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: ServiceErrorCode = ServiceErrorCode.PERMISSION_DENIED,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class AgentCredentialMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential_id: str
    agent_id: str
    owner_type: str = "agent"
    owner_id: str = ""
    credential_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    last_used_at: str | None = None
    last_auth_status: str | None = None
    expires_at: str | None = None


class AgentResolvedAuth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auth_data: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, Any] = Field(default_factory=dict)
    cookies: dict[str, str] = Field(default_factory=dict)
    body_fields: dict[str, Any] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    arguments: list[str] = Field(default_factory=list)
    stdin_input: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    refreshable: bool = False


@dataclass
class _SessionCacheEntry:
    auth_data: dict[str, Any]
    expires_at: datetime | None


@dataclass(frozen=True)
class _AuthTarget:
    owner_type: str
    owner_id: str
    endpoint: str
    auth_config: dict[str, Any]

    @property
    def agent_id(self) -> str:
        return self.owner_id

    @property
    def tool_name(self) -> str:
        return self.owner_id

    @property
    def server_id(self) -> str:
        return self.owner_id

    @property
    def transport_type(self) -> str:
        return str(self.auth_config.get("transport_type") or "")


class AgentCredentialVault:
    """SQLite-backed encrypted credential vault for external Agent auth."""

    FORMAT = "zentex_agent_credential_v1"

    def __init__(self, db: DatabaseConnection, *, master_key: str | None = None) -> None:
        self.db = db
        self._master_key = master_key or os.environ.get("ZENTEX_AGENT_AUTH_MASTER_KEY")
        self._lock = threading.Lock()
        self.ensure_schema()

    @classmethod
    def default(cls) -> "AgentCredentialVault":
        return cls(DatabaseConnection(str(get_storage_paths().core_db)))

    @property
    def is_configured(self) -> bool:
        return bool(self._master_key)

    def ensure_schema(self) -> None:
        with self.db.get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_auth_credentials (
                    credential_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    owner_type TEXT NOT NULL DEFAULT 'agent',
                    owner_id TEXT,
                    credential_type TEXT NOT NULL,
                    encrypted_payload_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_used_at TEXT,
                    last_auth_status TEXT,
                    expires_at TEXT
                );
                """
            )
            existing_columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(agent_auth_credentials)").fetchall()
            }
            for column, ddl in {
                "owner_type": "ALTER TABLE agent_auth_credentials ADD COLUMN owner_type TEXT NOT NULL DEFAULT 'agent'",
                "owner_id": "ALTER TABLE agent_auth_credentials ADD COLUMN owner_id TEXT",
            }.items():
                if column not in existing_columns:
                    conn.execute(ddl)
            conn.execute(
                """
                UPDATE agent_auth_credentials
                SET owner_type = COALESCE(NULLIF(owner_type, ''), 'agent'),
                    owner_id = COALESCE(NULLIF(owner_id, ''), agent_id)
                WHERE owner_id IS NULL OR owner_id = '' OR owner_type IS NULL OR owner_type = ''
                """
            )
            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_agent_auth_credentials_agent_id
                    ON agent_auth_credentials(agent_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_agent_auth_credentials_owner
                    ON agent_auth_credentials(owner_type, owner_id, updated_at DESC);
                """
            )

    def store_credential(
        self,
        *,
        agent_id: str,
        owner_type: str = "agent",
        owner_id: str | None = None,
        credential_type: str,
        secret_payload: dict[str, Any],
        credential_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentCredentialMetadata:
        self._require_key()
        credential_id = credential_id or f"agent_cred_{secrets.token_urlsafe(12).replace('-', '').replace('_', '')}"
        now = _now()
        encrypted = self._encrypt(credential_id, secret_payload)
        existing = self.get_metadata(credential_id)
        created_at = existing.created_at if existing else now
        self.db.execute_update(
            """
            INSERT INTO agent_auth_credentials (
                credential_id, agent_id, owner_type, owner_id, credential_type, encrypted_payload_json,
                metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(credential_id) DO UPDATE SET
                agent_id = excluded.agent_id,
                owner_type = excluded.owner_type,
                owner_id = excluded.owner_id,
                credential_type = excluded.credential_type,
                encrypted_payload_json = excluded.encrypted_payload_json,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                credential_id,
                agent_id,
                owner_type,
                owner_id or agent_id,
                credential_type,
                encrypted,
                _json(redact_sensitive(metadata or {})),
                created_at,
                now,
            ),
        )
        record = self.get_metadata(credential_id)
        if record is None:
            raise AgentAuthError("Credential write failed", code=ServiceErrorCode.INTERNAL_UNRECOVERABLE)
        return record

    def get_secret(
        self,
        credential_id: str,
        *,
        agent_id: str | None = None,
        owner_type: str | None = None,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_key()
        rows = self.db.execute_query(
            "SELECT * FROM agent_auth_credentials WHERE credential_id = ? LIMIT 1",
            (credential_id,),
        )
        if not rows:
            raise AgentAuthError("Credential not found", code=ServiceErrorCode.INVALID_ARGUMENT)
        row = dict(rows[0])
        if agent_id and row.get("agent_id") != agent_id:
            raise AgentAuthError("Credential does not belong to agent", code=ServiceErrorCode.PERMISSION_DENIED)
        if owner_type and row.get("owner_type") != owner_type:
            raise AgentAuthError("Credential owner_type mismatch", code=ServiceErrorCode.PERMISSION_DENIED)
        if owner_id and (row.get("owner_id") or row.get("agent_id")) != owner_id:
            raise AgentAuthError("Credential owner_id mismatch", code=ServiceErrorCode.PERMISSION_DENIED)
        return self._decrypt(credential_id, row["encrypted_payload_json"])

    def get_metadata(self, credential_id: str) -> AgentCredentialMetadata | None:
        rows = self.db.execute_query(
            "SELECT * FROM agent_auth_credentials WHERE credential_id = ? LIMIT 1",
            (credential_id,),
        )
        return self._row_to_metadata(rows[0]) if rows else None

    def list_metadata(self, agent_id: str) -> list[AgentCredentialMetadata]:
        rows = self.db.execute_query(
            """
            SELECT * FROM agent_auth_credentials
            WHERE agent_id = ?
            ORDER BY updated_at DESC
            """,
            (agent_id,),
        )
        return [self._row_to_metadata(row) for row in rows]

    def list_metadata_for_owner(self, owner_type: str, owner_id: str) -> list[AgentCredentialMetadata]:
        rows = self.db.execute_query(
            """
            SELECT * FROM agent_auth_credentials
            WHERE owner_type = ? AND owner_id = ?
            ORDER BY updated_at DESC
            """,
            (owner_type, owner_id),
        )
        return [self._row_to_metadata(row) for row in rows]

    def delete_credential(
        self,
        credential_id: str,
        *,
        agent_id: str | None = None,
        owner_type: str | None = None,
        owner_id: str | None = None,
    ) -> bool:
        if owner_type and owner_id:
            count = self.db.execute_update(
                "DELETE FROM agent_auth_credentials WHERE credential_id = ? AND owner_type = ? AND owner_id = ?",
                (credential_id, owner_type, owner_id),
            )
        elif agent_id:
            count = self.db.execute_update(
                "DELETE FROM agent_auth_credentials WHERE credential_id = ? AND agent_id = ?",
                (credential_id, agent_id),
            )
        else:
            count = self.db.execute_update(
                "DELETE FROM agent_auth_credentials WHERE credential_id = ?",
                (credential_id,),
            )
        return count > 0

    def mark_used(
        self,
        credential_id: str,
        *,
        status: str,
        expires_at: datetime | None = None,
    ) -> None:
        now = _now()
        self.db.execute_update(
            """
            UPDATE agent_auth_credentials
            SET last_used_at = ?,
                last_auth_status = ?,
                expires_at = COALESCE(?, expires_at),
                updated_at = ?
            WHERE credential_id = ?
            """,
            (now, status, expires_at.isoformat() if expires_at else None, now, credential_id),
        )

    def _row_to_metadata(self, row: Any) -> AgentCredentialMetadata:
        data = dict(row)
        return AgentCredentialMetadata(
            credential_id=data["credential_id"],
            agent_id=data["agent_id"],
            owner_type=data.get("owner_type") or "agent",
            owner_id=data.get("owner_id") or data["agent_id"],
            credential_type=data["credential_type"],
            metadata=_loads(data.get("metadata_json"), {}),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            last_used_at=data.get("last_used_at"),
            last_auth_status=data.get("last_auth_status"),
            expires_at=data.get("expires_at"),
        )

    def _require_key(self) -> None:
        if not self._master_key:
            raise AgentAuthError(
                "Agent credential vault is not configured: missing ZENTEX_AGENT_AUTH_MASTER_KEY",
                code=ServiceErrorCode.DEPENDENCY_UNAVAILABLE,
            )

    def _key(self) -> bytes:
        self._require_key()
        return hashlib.sha256(str(self._master_key).encode("utf-8")).digest()

    def _encrypt(self, credential_id: str, payload: dict[str, Any]) -> str:
        nonce = os.urandom(12)
        plaintext = _json(payload).encode("utf-8")
        ciphertext = AESGCM(self._key()).encrypt(nonce, plaintext, credential_id.encode("utf-8"))
        return _json(
            {
                "format": self.FORMAT,
                "nonce_b64": _b64(nonce),
                "ciphertext_b64": _b64(ciphertext),
            }
        )

    def _decrypt(self, credential_id: str, encrypted_payload_json: str) -> dict[str, Any]:
        stored = _loads(encrypted_payload_json, {})
        if stored.get("format") != self.FORMAT:
            raise AgentAuthError("Unsupported credential payload format", code=ServiceErrorCode.INTERNAL_UNRECOVERABLE)
        plaintext = AESGCM(self._key()).decrypt(
            _unb64(str(stored["nonce_b64"])),
            _unb64(str(stored["ciphertext_b64"])),
            credential_id.encode("utf-8"),
        )
        payload = json.loads(plaintext.decode("utf-8"))
        return payload if isinstance(payload, dict) else {}


class AgentAuthService:
    """Resolve Zentex-local auth_config into request auth material."""

    def __init__(self, vault: AgentCredentialVault | None = None) -> None:
        self.vault = vault or AgentCredentialVault.default()
        self._session_cache: dict[str, _SessionCacheEntry] = {}
        self._lock = threading.Lock()

    def credential_summary(self, agent_id: str) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self.vault.list_metadata(agent_id)]

    def credential_summary_for_owner(self, owner_type: str, owner_id: str) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self.vault.list_metadata_for_owner(owner_type, owner_id)]

    def store_credential(
        self,
        *,
        agent_id: str,
        credential_type: str,
        secret_payload: dict[str, Any],
        credential_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        owner_type: str = "agent",
        owner_id: str | None = None,
    ) -> AgentCredentialMetadata:
        return self.vault.store_credential(
            agent_id=agent_id,
            owner_type=owner_type,
            owner_id=owner_id or agent_id,
            credential_type=credential_type,
            secret_payload=secret_payload,
            credential_id=credential_id,
            metadata=metadata,
        )

    def delete_credential(self, *, agent_id: str, credential_id: str) -> bool:
        with self._lock:
            self._session_cache.pop(credential_id, None)
        return self.vault.delete_credential(credential_id, agent_id=agent_id)

    def delete_credential_for_owner(self, *, owner_type: str, owner_id: str, credential_id: str) -> bool:
        with self._lock:
            self._session_cache.pop(credential_id, None)
        return self.vault.delete_credential(credential_id, owner_type=owner_type, owner_id=owner_id)

    async def resolve(self, asset: Any, *, force_refresh: bool = False) -> AgentResolvedAuth:
        auth_config = dict(getattr(asset, "auth_config", {}) or {})
        legacy_token = getattr(asset, "auth_token", None)
        if not auth_config and not legacy_token:
            return AgentResolvedAuth()

        if not auth_config and legacy_token:
            auth_config = {"type": "bearer_token"}
            auth_data = {"access_token": legacy_token, "token": legacy_token}
            return self._build_resolved(auth_config, auth_data, refreshable=False)

        auth_type = str(auth_config.get("type") or "").strip()
        if not auth_type or auth_type == "none":
            return AgentResolvedAuth()

        credential_ref = str(auth_config.get("credential_ref") or "").strip()
        if not credential_ref:
            raise AgentAuthError("auth_config requires credential_ref", code=ServiceErrorCode.INVALID_ARGUMENT)

        if auth_type in {"bearer_token", "api_key", "basic"}:
            secret_payload = self.vault.get_secret(
                credential_ref,
                owner_type=getattr(asset, "owner_type", "agent"),
                owner_id=getattr(asset, "owner_id", getattr(asset, "agent_id", "")),
            )
            auth_data = self._static_auth_data(auth_type, secret_payload)
            self.vault.mark_used(credential_ref, status="resolved")
            return self._build_resolved(auth_config, auth_data, refreshable=False)

        if auth_type == "login_flow":
            auth_data, expires_at = await self._login_flow(asset, auth_config, credential_ref, force_refresh=force_refresh)
            self.vault.mark_used(credential_ref, status="login_ok", expires_at=expires_at)
            return self._build_resolved(auth_config, auth_data, refreshable=True)

        if auth_type == "oauth2_client_credentials":
            auth_data, expires_at = await self._oauth2_client_credentials(asset, auth_config, credential_ref, force_refresh=force_refresh)
            self.vault.mark_used(credential_ref, status="oauth_ok", expires_at=expires_at)
            return self._build_resolved(auth_config, auth_data, refreshable=True)

        raise AgentAuthError(f"Unsupported auth_config.type: {auth_type}", code=ServiceErrorCode.INVALID_ARGUMENT)

    async def resolve_owner(
        self,
        *,
        owner_type: str,
        owner_id: str,
        auth_config: dict[str, Any] | None,
        endpoint: str = "",
        force_refresh: bool = False,
    ) -> AgentResolvedAuth:
        target = _AuthTarget(owner_type=owner_type, owner_id=owner_id, endpoint=endpoint, auth_config=dict(auth_config or {}))
        if owner_type == "cli":
            return self.resolve_cli(target, force_refresh=force_refresh)
        if owner_type == "mcp":
            return self.resolve_mcp(target, force_refresh=force_refresh)
        return await self.resolve(target, force_refresh=force_refresh)

    def resolve_cli(self, config: Any, *, force_refresh: bool = False) -> AgentResolvedAuth:
        auth_config = dict(getattr(config, "auth_config", {}) or {})
        auth_type = str(auth_config.get("type") or "").strip()
        if not auth_type or auth_type == "none":
            return AgentResolvedAuth()
        credential_ref = str(auth_config.get("credential_ref") or "").strip()
        if not credential_ref:
            raise AgentAuthError("auth_config requires credential_ref", code=ServiceErrorCode.INVALID_ARGUMENT)
        owner_id = str(getattr(config, "tool_name", "") or "")
        if auth_type == "api_key":
            secret_payload = self.vault.get_secret(credential_ref, owner_type="cli", owner_id=owner_id)
            auth_data = self._static_auth_data("api_key", secret_payload)
            self.vault.mark_used(credential_ref, status="resolved")
            return self._build_cli_resolved(auth_config, auth_data, refreshable=False)
        if auth_type == "login_flow":
            auth_data, expires_at = self._cli_login_flow(config, auth_config, credential_ref, force_refresh=force_refresh)
            self.vault.mark_used(credential_ref, status="login_ok", expires_at=expires_at)
            return self._build_cli_resolved(auth_config, auth_data, refreshable=True)
        raise AgentAuthError(f"Unsupported CLI auth_config.type: {auth_type}", code=ServiceErrorCode.INVALID_ARGUMENT)

    def resolve_mcp(self, config: Any, *, force_refresh: bool = False) -> AgentResolvedAuth:
        auth_config = dict(getattr(config, "auth_config", {}) or {})
        auth_mode = str(getattr(config, "auth_mode", "none") or "none")
        if auth_mode in {"bearer", "api_key", "oauth_pkce"}:
            default_type = "api_key" if auth_mode == "api_key" else "bearer_token"
            if auth_mode == "oauth_pkce":
                default_type = "oauth_pkce"
            auth_config = {"type": default_type, **auth_config}
        auth_type = str(auth_config.get("type") or "").strip()
        if not auth_type or auth_type == "none":
            return AgentResolvedAuth()
        credential_ref = str(auth_config.get("credential_ref") or "").strip()
        if not credential_ref:
            raise AgentAuthError("auth_config requires credential_ref", code=ServiceErrorCode.INVALID_ARGUMENT)
        owner_id = str(getattr(config, "server_id", "") or "")
        if auth_type in {"api_key", "bearer_token", "oauth_pkce"}:
            secret_payload = self.vault.get_secret(credential_ref, owner_type="mcp", owner_id=owner_id)
            static_type = "bearer_token" if auth_type == "oauth_pkce" else auth_type
            auth_data = self._static_auth_data(static_type, secret_payload)
            self.vault.mark_used(credential_ref, status="resolved")
            return self._build_mcp_resolved(config, auth_config, auth_data, refreshable=False)
        if auth_type == "login_flow":
            auth_data, expires_at = self._mcp_login_flow(config, auth_config, credential_ref, force_refresh=force_refresh)
            self.vault.mark_used(credential_ref, status="login_ok", expires_at=expires_at)
            return self._build_mcp_resolved(config, auth_config, auth_data, refreshable=True)
        raise AgentAuthError(f"Unsupported MCP auth_config.type: {auth_type}", code=ServiceErrorCode.INVALID_ARGUMENT)

    def resolve_mcp_login_tool(
        self,
        config: Any,
        *,
        login_callable: Any,
        force_refresh: bool = False,
    ) -> AgentResolvedAuth:
        auth_config = dict(getattr(config, "auth_config", {}) or {})
        credential_ref = str(auth_config.get("credential_ref") or "").strip()
        if not credential_ref:
            raise AgentAuthError("auth_config requires credential_ref", code=ServiceErrorCode.INVALID_ARGUMENT)
        auth_data, expires_at = self._mcp_login_tool_flow(
            config,
            auth_config,
            credential_ref,
            login_callable=login_callable,
            force_refresh=force_refresh,
        )
        self.vault.mark_used(credential_ref, status="login_ok", expires_at=expires_at)
        return self._build_mcp_resolved(config, auth_config, auth_data, refreshable=True)

    async def _login_flow(
        self,
        asset: Any,
        auth_config: dict[str, Any],
        credential_ref: str,
        *,
        force_refresh: bool,
    ) -> tuple[dict[str, Any], datetime | None]:
        cached = self._get_cached(credential_ref, force_refresh=force_refresh)
        if cached is not None:
            return cached.auth_data, cached.expires_at

        secret_payload = self.vault.get_secret(
            credential_ref,
            owner_type=getattr(asset, "owner_type", "agent"),
            owner_id=getattr(asset, "owner_id", getattr(asset, "agent_id", "")),
        )
        login_config = dict(auth_config.get("login_request") or auth_config.get("login") or {})
        if not login_config:
            raise AgentAuthError("login_flow requires login_request", code=ServiceErrorCode.INVALID_ARGUMENT)

        root = {"credential": secret_payload, "auth": secret_payload, "agent": _agent_public_data(asset)}
        url = _auth_url(asset, login_config, root)
        method = str(login_config.get("method") or "POST").upper()
        headers = _render(login_config.get("headers", {}), root)
        body = _render(login_config.get("body_template", secret_payload), root)
        timeout = float(login_config.get("timeout", auth_config.get("timeout", 15.0)))
        expected_status = int(login_config.get("expected_status", 200))
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method, url, headers=headers, json=body)
        if response.status_code != expected_status:
            self.vault.mark_used(credential_ref, status=f"login_http_{response.status_code}")
            raise AgentAuthError(
                f"Agent login_flow expected HTTP {expected_status}, got {response.status_code}",
                status_code=response.status_code,
            )
        payload = _response_payload(response)
        auth_data, expires_at = self._token_payload(auth_config, payload)
        with self._lock:
            self._session_cache[credential_ref] = _SessionCacheEntry(auth_data=auth_data, expires_at=expires_at)
        return auth_data, expires_at

    async def _oauth2_client_credentials(
        self,
        asset: Any,
        auth_config: dict[str, Any],
        credential_ref: str,
        *,
        force_refresh: bool,
    ) -> tuple[dict[str, Any], datetime | None]:
        cached = self._get_cached(credential_ref, force_refresh=force_refresh)
        if cached is not None:
            return cached.auth_data, cached.expires_at

        secret_payload = self.vault.get_secret(
            credential_ref,
            owner_type=getattr(asset, "owner_type", "agent"),
            owner_id=getattr(asset, "owner_id", getattr(asset, "agent_id", "")),
        )
        root = {"credential": secret_payload, "auth": secret_payload, "agent": _agent_public_data(asset)}
        token_url = str(auth_config.get("token_url") or "").strip()
        if not token_url:
            token_url = _auth_url(asset, {"path": auth_config.get("token_path") or "/oauth/token"}, root)
        form_data = {
            "grant_type": "client_credentials",
            "client_id": secret_payload.get("client_id"),
            "client_secret": secret_payload.get("client_secret"),
        }
        scope = auth_config.get("scope") or auth_config.get("scopes")
        if isinstance(scope, list):
            form_data["scope"] = " ".join(str(item) for item in scope)
        elif scope:
            form_data["scope"] = str(scope)
        form_data.update(_render(auth_config.get("extra_token_fields", {}), root))
        headers = _render(auth_config.get("token_headers", {}), root)
        timeout = float(auth_config.get("timeout", 15.0))
        expected_status = int(auth_config.get("expected_status", 200))
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(token_url, headers=headers, data=form_data)
        if response.status_code != expected_status:
            self.vault.mark_used(credential_ref, status=f"oauth_http_{response.status_code}")
            raise AgentAuthError(
                f"OAuth2 token endpoint expected HTTP {expected_status}, got {response.status_code}",
                status_code=response.status_code,
            )
        payload = _response_payload(response)
        auth_data, expires_at = self._token_payload(auth_config, payload)
        with self._lock:
            self._session_cache[credential_ref] = _SessionCacheEntry(auth_data=auth_data, expires_at=expires_at)
        return auth_data, expires_at

    def _cli_login_flow(
        self,
        config: Any,
        auth_config: dict[str, Any],
        credential_ref: str,
        *,
        force_refresh: bool,
    ) -> tuple[dict[str, Any], datetime | None]:
        cached = self._get_cached(credential_ref, force_refresh=force_refresh)
        if cached is not None:
            return cached.auth_data, cached.expires_at
        owner_id = str(getattr(config, "tool_name", "") or "")
        secret_payload = self.vault.get_secret(credential_ref, owner_type="cli", owner_id=owner_id)
        login_config = dict(auth_config.get("login_command") or {})
        if not login_config:
            raise AgentAuthError("CLI login_flow requires login_command", code=ServiceErrorCode.INVALID_ARGUMENT)
        root = {"credential": secret_payload, "auth": secret_payload, "cli": _agent_public_data(config)}
        executable = str(_render(login_config.get("command_executable") or getattr(config, "command_executable", ""), root) or "")
        args = _render(login_config.get("args", []), root)
        stdin_input = _render(login_config.get("stdin_template"), root)
        env = {**dict(getattr(config, "env", {}) or {}), **_string_dict(_render(login_config.get("env", {}), root))}
        timeout = float(login_config.get("timeout_seconds", auth_config.get("timeout_seconds", 15.0)))
        if not executable:
            raise AgentAuthError("CLI login_command requires command_executable", code=ServiceErrorCode.INVALID_ARGUMENT)
        try:
            completed = subprocess.run(  # noqa: S603
                [executable, *[str(item) for item in (args if isinstance(args, list) else [])]],
                input=str(stdin_input) if stdin_input is not None else None,
                text=True,
                capture_output=True,
                env=env or None,
                timeout=timeout,
                check=False,
            )
        except (subprocess.TimeoutExpired, TimeoutError) as exc:
            raise AgentAuthError(f"CLI login_flow timed out: {exc}", code=ServiceErrorCode.SERVICE_TIMEOUT) from exc
        except (FileNotFoundError, PermissionError) as exc:
            raise AgentAuthError(f"CLI login_flow transport failed: {exc}", code=ServiceErrorCode.DEPENDENCY_UNAVAILABLE) from exc
        if completed.returncode != int(login_config.get("expected_exit_code", 0)):
            raise AgentAuthError(
                f"CLI login_flow failed with exit code {completed.returncode}: {completed.stderr}",
                code=ServiceErrorCode.PERMISSION_DENIED,
            )
        payload: Any
        try:
            payload = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise AgentAuthError("CLI login_flow stdout must be JSON", code=ServiceErrorCode.INVALID_ARGUMENT) from exc
        auth_data, expires_at = self._token_payload(auth_config, payload)
        with self._lock:
            self._session_cache[credential_ref] = _SessionCacheEntry(auth_data=auth_data, expires_at=expires_at)
        return auth_data, expires_at

    def _mcp_login_flow(
        self,
        config: Any,
        auth_config: dict[str, Any],
        credential_ref: str,
        *,
        force_refresh: bool,
    ) -> tuple[dict[str, Any], datetime | None]:
        cached = self._get_cached(credential_ref, force_refresh=force_refresh)
        if cached is not None:
            return cached.auth_data, cached.expires_at
        owner_id = str(getattr(config, "server_id", "") or "")
        secret_payload = self.vault.get_secret(credential_ref, owner_type="mcp", owner_id=owner_id)
        login_http = auth_config.get("login_http")
        if not isinstance(login_http, dict):
            raise AgentAuthError("MCP login_flow requires login_http in this phase", code=ServiceErrorCode.INVALID_ARGUMENT)
        root = {"credential": secret_payload, "auth": secret_payload, "mcp": _agent_public_data(config)}
        url = str(_render(login_http.get("url") or login_http.get("token_url") or "", root) or "")
        if not url:
            base = str(getattr(config, "command", "") or "")
            path = str(_render(login_http.get("path", ""), root) or "")
            url = base.rstrip("/") + "/" + path.lstrip("/") if path else base
        method = str(login_http.get("method") or "POST").upper()
        headers = _string_dict(_render(login_http.get("headers", {}), root))
        body = _render(login_http.get("body_template", secret_payload), root)
        timeout = float(login_http.get("timeout", auth_config.get("timeout", 15.0)))
        expected_status = int(login_http.get("expected_status", 200))
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.request(method, url, headers=headers, json=body)
        except httpx.RequestError as exc:
            raise AgentAuthError(f"MCP login_flow transport failed: {exc}", code=ServiceErrorCode.DEPENDENCY_UNAVAILABLE) from exc
        if response.status_code != expected_status:
            raise AgentAuthError(
                f"MCP login_flow expected HTTP {expected_status}, got {response.status_code}",
                status_code=response.status_code,
            )
        payload = _response_payload(response)
        auth_data, expires_at = self._token_payload(auth_config, payload)
        with self._lock:
            self._session_cache[credential_ref] = _SessionCacheEntry(auth_data=auth_data, expires_at=expires_at)
        return auth_data, expires_at

    def _mcp_login_tool_flow(
        self,
        config: Any,
        auth_config: dict[str, Any],
        credential_ref: str,
        *,
        login_callable: Any,
        force_refresh: bool,
    ) -> tuple[dict[str, Any], datetime | None]:
        cached = self._get_cached(credential_ref, force_refresh=force_refresh)
        if cached is not None:
            return cached.auth_data, cached.expires_at
        owner_id = str(getattr(config, "server_id", "") or "")
        secret_payload = self.vault.get_secret(credential_ref, owner_type="mcp", owner_id=owner_id)
        login_tool = auth_config.get("login_tool")
        if not isinstance(login_tool, dict):
            raise AgentAuthError("MCP login_flow requires login_tool", code=ServiceErrorCode.INVALID_ARGUMENT)
        tool_name = str(login_tool.get("tool_name") or login_tool.get("name") or "").strip()
        if not tool_name:
            raise AgentAuthError("MCP login_tool requires tool_name", code=ServiceErrorCode.INVALID_ARGUMENT)
        root = {"credential": secret_payload, "auth": secret_payload, "mcp": _agent_public_data(config)}
        rendered_arguments = _render(
            login_tool.get("arguments_template", login_tool.get("arguments", secret_payload)),
            root,
        )
        if not isinstance(rendered_arguments, dict):
            raise AgentAuthError("MCP login_tool arguments must render to an object", code=ServiceErrorCode.INVALID_ARGUMENT)
        try:
            payload = login_callable(tool_name, rendered_arguments)
        except AgentAuthError:
            raise
        except PermissionError as exc:
            raise AgentAuthError(f"MCP login_tool permission denied: {exc}", code=ServiceErrorCode.PERMISSION_DENIED) from exc
        except (TimeoutError, subprocess.TimeoutExpired) as exc:
            raise AgentAuthError(f"MCP login_tool timed out: {exc}", code=ServiceErrorCode.SERVICE_TIMEOUT) from exc
        except Exception as exc:
            raise AgentAuthError(f"MCP login_tool transport failed: {exc}", code=ServiceErrorCode.DEPENDENCY_UNAVAILABLE) from exc
        auth_data, expires_at = self._token_payload(auth_config, payload)
        with self._lock:
            self._session_cache[credential_ref] = _SessionCacheEntry(auth_data=auth_data, expires_at=expires_at)
        return auth_data, expires_at

    def _get_cached(self, credential_ref: str, *, force_refresh: bool) -> _SessionCacheEntry | None:
        if force_refresh:
            with self._lock:
                self._session_cache.pop(credential_ref, None)
            return None
        with self._lock:
            cached = self._session_cache.get(credential_ref)
        if cached is None:
            return None
        if cached.expires_at is None or cached.expires_at > datetime.now(UTC):
            return cached
        with self._lock:
            self._session_cache.pop(credential_ref, None)
        return None

    @staticmethod
    def _static_auth_data(auth_type: str, secret_payload: dict[str, Any]) -> dict[str, Any]:
        if auth_type == "bearer_token":
            token = secret_payload.get("access_token") or secret_payload.get("token") or secret_payload.get("bearer_token")
            if not token:
                raise AgentAuthError("bearer_token credential requires token", code=ServiceErrorCode.INVALID_ARGUMENT)
            return {"access_token": token, "token": token}
        if auth_type == "api_key":
            api_key = secret_payload.get("api_key") or secret_payload.get("key") or secret_payload.get("token")
            if not api_key:
                raise AgentAuthError("api_key credential requires api_key", code=ServiceErrorCode.INVALID_ARGUMENT)
            return {"api_key": api_key, "key": api_key}
        if auth_type == "basic":
            username = secret_payload.get("username")
            password = secret_payload.get("password")
            if username is None or password is None:
                raise AgentAuthError("basic credential requires username and password", code=ServiceErrorCode.INVALID_ARGUMENT)
            raw = f"{username}:{password}".encode("utf-8")
            return {
                "username": username,
                "password": password,
                "basic_token": base64.b64encode(raw).decode("ascii"),
            }
        return dict(secret_payload)

    def _token_payload(self, auth_config: dict[str, Any], payload: Any) -> tuple[dict[str, Any], datetime | None]:
        if not isinstance(payload, dict):
            raise AgentAuthError("Auth token response must be a JSON object", code=ServiceErrorCode.INVALID_ARGUMENT)
        access_path = str(auth_config.get("access_token_path") or "access_token")
        token = _lookup(payload, access_path)
        refresh_path = auth_config.get("refresh_token_path")
        expires_path = str(auth_config.get("expires_in_path") or "expires_in")
        expires_in = _lookup_optional(payload, expires_path)
        skew_seconds = int(auth_config.get("refresh_skew_seconds", 30))
        expires_at: datetime | None = None
        if expires_in is not None:
            expires_at = datetime.now(UTC) + timedelta(seconds=max(0, int(float(expires_in)) - skew_seconds))
        auth_data = {
            "access_token": token,
            "token": token,
            "token_type": payload.get("token_type", "Bearer"),
            "expires_at": expires_at.isoformat() if expires_at else None,
        }
        if refresh_path:
            refresh_token = _lookup_optional(payload, str(refresh_path))
            if refresh_token is not None:
                auth_data["refresh_token"] = refresh_token
        return auth_data, expires_at

    def _build_resolved(self, auth_config: dict[str, Any], auth_data: dict[str, Any], *, refreshable: bool) -> AgentResolvedAuth:
        inject = auth_config.get("inject")
        if not isinstance(inject, dict):
            inject = self._default_inject(auth_config, auth_data)
        root = {"auth": auth_data}
        headers = _string_dict(_render(inject.get("headers", {}), root))
        query = _render(inject.get("query", inject.get("params", {})), root)
        cookies = _string_dict(_render(inject.get("cookies", {}), root))
        body_fields = _render(inject.get("body", inject.get("body_fields", {})), root)
        return AgentResolvedAuth(
            auth_data=auth_data,
            headers=headers,
            query=query if isinstance(query, dict) else {},
            cookies=cookies,
            body_fields=body_fields if isinstance(body_fields, dict) else {},
            metadata={
                "auth_type": auth_config.get("type") or "none",
                "credential_ref": auth_config.get("credential_ref"),
            },
            refreshable=refreshable,
        )

    def _build_cli_resolved(self, auth_config: dict[str, Any], auth_data: dict[str, Any], *, refreshable: bool) -> AgentResolvedAuth:
        inject = auth_config.get("inject")
        if not isinstance(inject, dict):
            inject = self._default_cli_inject(auth_config, auth_data)
        root = {"auth": auth_data}
        rendered_args = _render(inject.get("arguments", []), root)
        rendered_stdin = _render(inject.get("stdin_template"), root) if "stdin_template" in inject else None
        return AgentResolvedAuth(
            auth_data=auth_data,
            env=_string_dict(_render(inject.get("env", {}), root)),
            arguments=[str(item) for item in rendered_args] if isinstance(rendered_args, list) else [],
            stdin_input=str(rendered_stdin) if rendered_stdin is not None else None,
            metadata={"auth_type": auth_config.get("type") or "none", "credential_ref": auth_config.get("credential_ref")},
            refreshable=refreshable,
        )

    def _build_mcp_resolved(self, config: Any, auth_config: dict[str, Any], auth_data: dict[str, Any], *, refreshable: bool) -> AgentResolvedAuth:
        inject = auth_config.get("inject")
        if not isinstance(inject, dict):
            inject = self._default_mcp_inject(config, auth_config, auth_data)
        root = {"auth": auth_data}
        arguments = _render(inject.get("arguments", {}), root)
        return AgentResolvedAuth(
            auth_data=auth_data,
            headers=_string_dict(_render(inject.get("headers", {}), root)),
            query=_render(inject.get("query", inject.get("params", {})), root) if isinstance(inject, dict) else {},
            env=_string_dict(_render(inject.get("env", {}), root)),
            body_fields=arguments if isinstance(arguments, dict) else {},
            metadata={"auth_type": auth_config.get("type") or "none", "credential_ref": auth_config.get("credential_ref")},
            refreshable=refreshable,
        )

    @staticmethod
    def _default_inject(auth_config: dict[str, Any], auth_data: dict[str, Any]) -> dict[str, Any]:
        auth_type = str(auth_config.get("type") or "")
        if auth_type in {"bearer_token", "login_flow", "oauth2_client_credentials", "oauth_pkce"}:
            token_type = str(auth_data.get("token_type") or "Bearer")
            return {"headers": {"Authorization": f"{token_type} $auth.access_token"}}
        if auth_type == "basic":
            return {"headers": {"Authorization": "Basic $auth.basic_token"}}
        if auth_type == "api_key":
            location = str(auth_config.get("location") or "headers")
            key_name = str(auth_config.get("key_name") or auth_config.get("header_name") or "X-API-Key")
            if location == "query":
                return {"query": {key_name: "$auth.api_key"}}
            if location == "body":
                return {"body": {key_name: "$auth.api_key"}}
            return {"headers": {key_name: "$auth.api_key"}}
        return {}

    @staticmethod
    def _default_cli_inject(auth_config: dict[str, Any], auth_data: dict[str, Any]) -> dict[str, Any]:
        auth_type = str(auth_config.get("type") or "")
        if auth_type == "api_key":
            return {"env": {str(auth_config.get("env_name") or "ZENTEX_CLI_API_KEY"): "$auth.api_key"}}
        if auth_type == "login_flow":
            return {"env": {str(auth_config.get("env_name") or "ZENTEX_CLI_ACCESS_TOKEN"): "$auth.access_token"}}
        return {}

    @staticmethod
    def _default_mcp_inject(config: Any, auth_config: dict[str, Any], auth_data: dict[str, Any]) -> dict[str, Any]:
        auth_type = str(auth_config.get("type") or "")
        transport_type = str(getattr(config, "transport_type", "") or "")
        if transport_type == "stdio":
            if auth_type == "api_key":
                return {"env": {str(auth_config.get("env_name") or "ZENTEX_MCP_API_KEY"): "$auth.api_key"}}
            return {"env": {str(auth_config.get("env_name") or "ZENTEX_MCP_ACCESS_TOKEN"): "$auth.access_token"}}
        if auth_type == "api_key":
            key_name = str(auth_config.get("key_name") or auth_config.get("header_name") or "X-API-Key")
            return {"headers": {key_name: "$auth.api_key"}}
        token_type = str(auth_data.get("token_type") or "Bearer")
        return {"headers": {"Authorization": f"{token_type} $auth.access_token"}}


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value


def public_auth_config(auth_config: dict[str, Any] | None) -> dict[str, Any]:
    config = dict(auth_config or {})
    return _redact_direct_secret_fields(config)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(token in lowered for token in _SENSITIVE_KEY_TOKENS)


def _redact_direct_secret_fields(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower().replace("-", "_")
            if lowered in {
                "authorization",
                "cookie",
                "api_key",
                "access_token",
                "refresh_token",
                "auth_token",
                "bearer_token",
                "client_secret",
                "password",
                "secret",
                "token",
            }:
                if isinstance(item, str) and ("$auth." in item or "$credential." in item):
                    redacted[key] = item
                else:
                    redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact_direct_secret_fields(item)
        return redacted
    if isinstance(value, list):
        return [_redact_direct_secret_fields(item) for item in value]
    return value


def _agent_public_data(asset: Any) -> dict[str, Any]:
    if hasattr(asset, "model_dump"):
        data = asset.model_dump(mode="json")
    else:
        data = dict(getattr(asset, "__dict__", {}))
    data.pop("auth_token", None)
    return redact_sensitive(data)


def _auth_url(asset: Any, config: dict[str, Any], root: dict[str, Any]) -> str:
    if config.get("url"):
        return str(_render(config["url"], root))
    path = str(_render(config.get("path", ""), root) or "")
    endpoint = str(getattr(asset, "endpoint", "") or "")
    if path:
        return endpoint.rstrip("/") + "/" + path.lstrip("/")
    return endpoint


def _render(value: Any, root: dict[str, Any]) -> Any:
    from zentex.agents.adapters import AgentInvocationAdapter

    return AgentInvocationAdapter._render(value, root)


def _lookup(root: Any, path: str) -> Any:
    current = root
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                raise AgentAuthError(f"Auth response path not found: {path}", code=ServiceErrorCode.INVALID_ARGUMENT)
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                raise AgentAuthError(f"Auth response path not found: {path}", code=ServiceErrorCode.INVALID_ARGUMENT)
            current = current[index]
        else:
            raise AgentAuthError(f"Auth response path not found: {path}", code=ServiceErrorCode.INVALID_ARGUMENT)
    return current


def _lookup_optional(root: Any, path: str) -> Any:
    try:
        return _lookup(root, path)
    except AgentAuthError:
        return None


def _response_payload(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"text": response.text}


def _string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _loads(value: str | None, default: Any) -> Any:
    if value in {None, ""}:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"))
