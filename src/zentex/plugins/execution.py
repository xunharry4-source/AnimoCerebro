from __future__ import annotations
"""Public execution plugin contracts owned by zentex.plugins."""


from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from zentex.plugins.contracts import BasePluginSpec


class ActionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


class ActionIntent(BaseModel):
    model_config = ConfigDict(extra="allow")

    action_type: str
    target: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    requester_id: str = ""


class ActionExecutionReceipt(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: ActionStatus
    evidence_payload: dict[str, Any] = Field(default_factory=dict)


class ExecutionDomainPlugin(BasePluginSpec, ABC):
    execution_domain: str = "execution"

    @abstractmethod
    def execute_action(self, intent: ActionIntent, context: dict[str, Any]) -> ActionExecutionReceipt: ...
