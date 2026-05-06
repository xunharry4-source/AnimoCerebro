from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from zentex.module_logs import ModuleLogPage


router = APIRouter()


@router.get("/module-logs", response_model=ModuleLogPage)
def query_module_logs(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=40, ge=1, le=200),
    source_module: str | None = Query(default=None),
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
) -> ModuleLogPage:
    service = getattr(request.app.state, "module_log_service", None)
    if service is None or not callable(getattr(service, "query_logs", None)):
        raise HTTPException(status_code=503, detail="ModuleLogService is unavailable")
    return service.query_logs(
        page=page,
        page_size=page_size,
        source_module=source_module,
        status=status,
        search=search,
    )
