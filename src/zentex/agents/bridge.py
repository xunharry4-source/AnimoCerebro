"""
Agent Communication Bridge.
Handles standard protocol interactions with external/internal agents.
Implements: Handshake, Task Execution, and Health Monitoring.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone

import httpx

from zentex.agents.manager import AgentAsset, AgentStatus

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
        Step 1: Capability Discovery.
        Calls the agent's /handshake endpoint to verify identity and capabilities.
        """
        if "mock://" in asset.endpoint:
            # Mock behavior for development
            logger.info(f"Using MOCK handshake for {asset.agent_id}")
            return {
                "agent_id": asset.agent_id,
                "version": "1.0.0-mock",
                "capabilities": [{"name": "mock_echo"}],
                "status": "idle"
            }

        endpoint = f"{asset.endpoint.rstrip('/')}/handshake"
        headers = {}
        if asset.auth_token:
            headers["Authorization"] = f"Bearer {asset.auth_token}"

        try:
            logger.info(f"Initiating handshake with {asset.agent_id} at {endpoint}")
            logger.debug(f"Using headers: {headers}")
            
            # Add connection debugging
            response = await self._client.post(endpoint, headers=headers)
            logger.debug(f"Response status: {response.status_code}")
            
            response.raise_for_status()
            data = response.json()
            logger.debug(f"Handshake response data: {data}")
            
            # Validate basic handshake structure
            if "agent_id" not in data or "capabilities" not in data:
                raise ValueError("Invalid handshake response structure")
                
            logger.info(f"Handshake successful for {asset.agent_id}: {data.get('version')}")
            return data
        except Exception as e:
            logger.error(f"Handshake failed for {asset.agent_id}: {e}")
            raise

    async def execute_task(self, asset: AgentAsset, task_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Step 2: Task Dispatch.
        Sends a task to the agent's /execute endpoint.
        """
        if "mock://" in asset.endpoint:
            logger.info(f"Using MOCK execution for {asset.agent_id}")
            return {"status": "success", "result": "mock_response"}

        endpoint = f"{asset.endpoint.rstrip('/')}/execute"
        headers = {"Content-Type": "application/json"}
        if asset.auth_token:
            headers["Authorization"] = f"Bearer {asset.auth_token}"

        try:
            logger.info(f"Dispatching task to {asset.agent_id}")
            response = await self._client.post(endpoint, json=task_payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Task execution failed for {asset.agent_id}: {e}")
            raise

    async def check_health(self, asset: AgentAsset) -> bool:
        """
        Step 3: Health Check.
        Pings the agent's /status or root endpoint.
        """
        if "mock://" in asset.endpoint:
            return True

        endpoint = f"{asset.endpoint.rstrip('/')}/status"
        try:
            response = await self._client.get(endpoint, timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False
