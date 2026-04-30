from __future__ import annotations
"""
Legacy Agent Communication Bridge.

This file still contains the transitional fixed-path Bridge behavior. It is
kept for compatibility while zentex.agents moves toward adapter/mapping based
external capability invocation.
"""

import asyncio
import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone

import httpx

from zentex.agents.manager import AgentAsset, AgentStatus

class AgentBridgeError(Exception):
    """Base exception for all agent bridge communication failures."""
    def __init__(self, message: str, status_code: Optional[int] = None, detail: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


logger = logging.getLogger(__name__)


class AgentBridge:
    """
    Transitional network bridge for legacy HTTP Agent integrations.

    Do not treat these paths as a required external Agent protocol. New
    integrations should use adapter/mapping configuration instead.
    """

    def __init__(self, timeout: float = 30.0):
        self.timeout = httpx.Timeout(timeout)
        self._client = httpx.AsyncClient(timeout=self.timeout)
        logger.info(f"AgentBridge initialized with timeout={timeout}s")

    @staticmethod
    def _inject_local_agent_id(asset: AgentAsset, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a remote response with Zentex-local agent identity."""
        local_payload = dict(payload)
        remote_agent_id = local_payload.get("agent_id")
        if remote_agent_id and remote_agent_id != asset.agent_id:
            local_payload.setdefault("external_agent_id", remote_agent_id)
        local_payload["agent_id"] = asset.agent_id
        return local_payload

    async def close(self):
        await self._client.aclose()

    async def perform_handshake(self, asset: AgentAsset) -> Dict[str, Any]:
        """
        Optional legacy capability discovery.

        Calls the legacy /handshake endpoint when an external Agent happens to
        support it. This does not verify external identity and must not be a
        universal registration requirement.
        
        POLICY: agent_id is local to Zentex. A remote Agent does not need to
        return it; Zentex injects the local agent_id into the normalized
        response. If the remote response contains its own id, it is preserved as
        external_agent_id metadata.
        """
        endpoint = f"{asset.endpoint.rstrip('/')}/handshake"
        headers = {}
        if asset.auth_token:
            headers["Authorization"] = f"Bearer {asset.auth_token}"

        try:
            logger.info(f"Initiating handshake with {asset.agent_id} at {endpoint}")
            response = await self._client.post(endpoint, headers=headers)
            response.raise_for_status()
            data = self._inject_local_agent_id(asset, response.json())
            
            remote_id = data.get("external_agent_id")
            if remote_id:
                logger.info(
                    "Remote agent id differs from local asset id; treating remote id as metadata",
                    extra={
                        "local_agent_id": asset.agent_id,
                        "remote_agent_id": remote_id,
                        "endpoint": endpoint,
                    },
                )

            # Version Verification (Audit, not necessarily hard fail)
            remote_version = data.get("version")
            if remote_version and remote_version != asset.version:
                logger.warning(f"Agent Version Drift: {asset.agent_id} is at {remote_version}, registry says {asset.version}")

            # Structure Validation
            if "capabilities" not in data:
                raise AgentBridgeError("Invalid handshake response: missing 'capabilities' field")
                
            logger.info(f"Handshake successful for {asset.agent_id} (Version: {remote_version})")
            return data
        except httpx.HTTPStatusError as e:
            logger.error(f"Handshake failed for {asset.agent_id} (HTTP {e.response.status_code}): {e}")
            raise AgentBridgeError(f"Handshake HTTP error: {e}", status_code=e.response.status_code)
        except httpx.RequestError as e:
            logger.error(f"Handshake network error for {asset.agent_id}: {e}")
            raise AgentBridgeError(f"Handshake transport failure: {e}")
        except AgentBridgeError:
            raise # Re-raise specialized bridge errors
        except Exception as e:
            logger.error(f"Handshake unexpected error for {asset.agent_id}: {e}")
            raise AgentBridgeError(f"Handshake failed: {e}")


    async def execute_task(
        self,
        asset: AgentAsset,
        task_payload: Dict[str, Any],
        *,
        auth_headers: Dict[str, str] | None = None,
    ) -> Dict[str, Any]:
        """
        Legacy task dispatch through /execute.
        """
        endpoint = f"{asset.endpoint.rstrip('/')}/execute"
        headers = {"Content-Type": "application/json"}
        if asset.auth_token:
            headers["Authorization"] = f"Bearer {asset.auth_token}"
        if auth_headers:
            headers.update(auth_headers)

        try:
            logger.info(f"Dispatching task to {asset.agent_id}")
            response = await self._client.post(endpoint, json=task_payload, headers=headers)
            response.raise_for_status()
            return self._inject_local_agent_id(asset, response.json())
        except httpx.HTTPStatusError as e:
            logger.error(f"Task execution failed for {asset.agent_id} (HTTP {e.response.status_code}): {e}", exc_info=True)
            raise AgentBridgeError(f"Execution HTTP error: {e}", status_code=e.response.status_code)
        except httpx.RequestError as e:
            logger.error(f"Task execution network error for {asset.agent_id}: {e}", exc_info=True)
            raise AgentBridgeError(f"Execution transport failure: {e}")
        except Exception as e:
            logger.error(f"Task execution failed for {asset.agent_id}: {e}", exc_info=True)
            raise AgentBridgeError(f"Execution failed: {e}")


    async def check_health(self, asset: AgentAsset) -> bool:
        """
        Optional legacy health probe through /status.
        """
        endpoint = f"{asset.endpoint.rstrip('/')}/status"
        try:
            response = await self._client.get(endpoint, timeout=5.0)
            return response.status_code == 200
        except Exception:
            # POLICY[no-silent-except]: probe failure is expected when agent is down; log at DEBUG.
            logger.debug("Health check failed for agent at %s", endpoint, exc_info=True)
            return False
