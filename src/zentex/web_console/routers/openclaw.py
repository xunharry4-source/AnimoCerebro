from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from zentex.openclaw.bridge import OpenClawBridgeRequest, OpenClawBridgeRuntime

router = APIRouter(prefix="/openclaw", tags=["openclaw"])


def _runtime(request: Request) -> OpenClawBridgeRuntime:
    runtime = getattr(request.app.state, "openclaw_bridge_runtime", None)
    if runtime is None:
        runtime = OpenClawBridgeRuntime()
        request.app.state.openclaw_bridge_runtime = runtime
    return runtime


@router.post("/bridge/call")
def call_openclaw_bridge(payload: OpenClawBridgeRequest, request: Request) -> dict:
    try:
        return _runtime(request).call(payload).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "openclaw_bridge_rejected", "message": str(exc)}) from exc


@router.get("/bridge/audit/{request_id}")
def query_openclaw_bridge_audit(request_id: str, request: Request) -> dict:
    try:
        return _runtime(request).query_audit(request_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "openclaw_audit_not_found", "message": request_id}) from exc
