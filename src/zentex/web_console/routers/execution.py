from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from zentex.execution.models import ExecutionRequest


router = APIRouter()


def _get_service(request: Request):
    service = getattr(request.app.state, "execution_service", None)
    if service is not None:
        return service
    from zentex.execution.service import get_service

    service = get_service()
    request.app.state.execution_service = service
    return service


@router.post("/execution/actions")
def execute_action(payload: ExecutionRequest, request: Request):
    return _get_service(request).execute_action(payload)


@router.get("/execution/receipts/{receipt_id}")
def get_receipt(receipt_id: str, request: Request):
    receipt = _get_service(request).get_receipt(receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"ActionExecutionReceipt {receipt_id} not found")
    return receipt


@router.get("/execution/ledger/{key}")
def get_ledger_value(key: str, request: Request):
    return {"key": key, "value": _get_service(request).get_ledger_value(key)}
