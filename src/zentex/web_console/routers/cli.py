from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends

from zentex.cli.service import CliIntegrationService
from zentex.core.cli import CliToolRegistrationConfig
from zentex.web_console.contracts.cli import (
    CliToolItem,
    CliToolRegistrationRequest,
    CliToolTestCallRequest,
    CliToolTestCallResult,
)
from zentex.web_console.dependencies import get_cli_service


router = APIRouter()


@router.get("/cli-tools", response_model=List[CliToolItem])
def list_cli_tools(service: CliIntegrationService = Depends(get_cli_service)) -> List[CliToolItem]:
    return [CliToolItem.model_validate(item.model_dump(mode="json")) for item in service.list_tools()]


@router.post("/cli-tools/register", response_model=CliToolItem)
def register_cli_tool(
    payload: CliToolRegistrationRequest,
    service: CliIntegrationService = Depends(get_cli_service),
) -> CliToolItem:
    state = service.register_tool(CliToolRegistrationConfig.model_validate(payload.model_dump(mode="json")))
    return CliToolItem.model_validate(state.model_dump(mode="json"))


@router.post("/cli-tools/{tool_name}/test-call", response_model=CliToolTestCallResult)
def test_cli_tool(
    tool_name: str,
    payload: CliToolTestCallRequest,
    service: CliIntegrationService = Depends(get_cli_service),
) -> CliToolTestCallResult:
    result = service.test_call(
        tool_name,
        arguments=payload.arguments,
        stdin_input=payload.stdin_input,
        working_directory=payload.working_directory,
        timeout_seconds=payload.timeout_seconds,
    )
    return CliToolTestCallResult.model_validate(result.model_dump(mode="json"))
