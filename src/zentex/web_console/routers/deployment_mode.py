from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from zentex.deployment.mode import DeploymentModeConfig, DeploymentModeRuntime

router = APIRouter(prefix="/deployment-mode", tags=["deployment-mode"])


def _runtime(request: Request) -> DeploymentModeRuntime:
    runtime = getattr(request.app.state, "deployment_mode_runtime", None)
    if runtime is None:
        runtime = DeploymentModeRuntime()
        request.app.state.deployment_mode_runtime = runtime
    return runtime


@router.post("/configure")
def configure_deployment_mode(payload: DeploymentModeConfig, request: Request) -> dict:
    try:
        return _runtime(request).configure(payload).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "deployment_mode_rejected", "message": str(exc)}) from exc


@router.get("/state")
def query_deployment_mode(request: Request) -> dict:
    return _runtime(request).state().model_dump(mode="json")


@router.post("/sync-check")
def run_deployment_sync_check(request: Request) -> dict:
    return _runtime(request).sync_check().model_dump(mode="json")
