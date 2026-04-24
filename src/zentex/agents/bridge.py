from __future__ import annotations
"""
Agent Communication Bridge.
Handles standard protocol interactions with external/internal agents.
Implements: Handshake, Task Execution, and Health Monitoring.
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
    Manages network communication with registered agents.
    Enforces standard interaction protocols.
    """

    def __init__(self, timeout: float = 30.0):
        self.timeout = httpx.Timeout(timeout)
        self._client = httpx.AsyncClient(timeout=self.timeout)
        logger.info(f"AgentBridge initialized with timeout={timeout}s")

    async def close(self):
        await self._client.aclose()

    async def perform_handshake(self, asset: AgentAsset) -> Dict[str, Any]:
        """
        Step 1: Capability Discovery & Identity Verification.
        Calls the agent's /handshake endpoint to verify identity and capabilities.
        
        POLICY: Fail-Closed. Identity must be verified during handshake.
        """
        endpoint = f"{asset.endpoint.rstrip('/')}/handshake"
        headers = {}
        if asset.auth_token:
            headers["Authorization"] = f"Bearer {asset.auth_token}"

        try:
            logger.info(f"Initiating handshake with {asset.agent_id} at {endpoint}")
            response = await self._client.post(endpoint, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            # 1. Authentic Identity Verification
            remote_id = data.get("agent_id")
            if not remote_id:
                raise AgentBridgeError("Remote agent failed to provide agent_id during handshake")
                
            if remote_id != asset.agent_id:
                logger.critical(f"IDENTITY SPOOFING DETECTED: Expected {asset.agent_id}, got {remote_id} at {endpoint}")
                raise AgentBridgeError(
                    f"Identity mismatch: Remote claims to be {remote_id}, but we expected {asset.agent_id}",
                    status_code=403
                )
            
            # 2. Version Verification (Audit, not necessarily hard fail)
            remote_version = data.get("version")
            if remote_version and remote_version != asset.version:
                logger.warning(f"Agent Version Drift: {asset.agent_id} is at {remote_version}, registry says {asset.version}")

            # 3. Structure Validation
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


    async def execute_task(self, asset: AgentAsset, task_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Step 2: Task Dispatch.
        Sends a task to the agent's /execute endpoint.
        """
        endpoint = f"{asset.endpoint.rstrip('/')}/execute"
        headers = {"Content-Type": "application/json"}
        if asset.auth_token:
            headers["Authorization"] = f"Bearer {asset.auth_token}"

        try:
            logger.info(f"Dispatching task to {asset.agent_id}")
            response = await self._client.post(endpoint, json=task_payload, headers=headers)
            response.raise_for_status()
            return response.json()
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
        Step 3: Health Check.
        Pings the agent's /status or root endpoint.
        """
        endpoint = f"{asset.endpoint.rstrip('/')}/status"
        try:
            response = await self._client.get(endpoint, timeout=5.0)
            return response.status_code == 200
        except Exception:
            # POLICY[no-silent-except]: probe failure is expected when agent is down; log at DEBUG.
            logger.debug("Health check failed for agent at %s", endpoint, exc_info=True)
            return False
