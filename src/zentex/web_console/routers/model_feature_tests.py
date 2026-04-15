from __future__ import annotations
from typing import List, Optional


from fastapi import APIRouter, HTTPException, Request

from zentex.web_console.contracts.model_feature_tests import (
    ModelFeatureHistoryItem,
    ModelFeatureInvokeRequest,
    ModelFeatureInvokeResponse,
    ModelFeatureRunLogResponse,
    ModelFeatureStatsResponse,
    ModelFeatureTestCatalogItem,
)
from zentex.web_console.services.model_feature_tests import (
    collect_model_feature_stats,
    get_model_feature_history,
    get_model_feature_test_run_log,
    invoke_model_feature_test,
    list_model_feature_tests,
)


router = APIRouter()


@router.get("/tests/model-features", response_model=List[ModelFeatureTestCatalogItem])
def list_model_feature_tests_route() -> List[ModelFeatureTestCatalogItem]:
    return list_model_feature_tests()


@router.get("/tests/model-features/stats", response_model=ModelFeatureStatsResponse)
def get_model_feature_test_stats(feature_id: Optional[str] = None) -> ModelFeatureStatsResponse:
    return collect_model_feature_stats(feature_id=feature_id)


@router.get("/tests/model-features/history", response_model=List[ModelFeatureHistoryItem])
def get_model_feature_test_history(feature_id: str, limit: int = 20) -> List[ModelFeatureHistoryItem]:
    return get_model_feature_history(feature_id, limit=limit)


@router.get("/tests/model-features/{feature_id}/history", response_model=List[ModelFeatureHistoryItem])
def get_model_feature_test_history_by_path(feature_id: str, limit: int = 20) -> List[ModelFeatureHistoryItem]:
    return get_model_feature_history(feature_id, limit=limit)


@router.get("/tests/model-features/run-log", response_model=ModelFeatureRunLogResponse)
def get_model_feature_test_run_log_route(test_run_id: str) -> ModelFeatureRunLogResponse:
    return get_model_feature_test_run_log(test_run_id)


@router.get("/tests/model-features/runs/{test_run_id}", response_model=ModelFeatureRunLogResponse)
def get_model_feature_test_run_log_by_path(test_run_id: str) -> ModelFeatureRunLogResponse:
    return get_model_feature_test_run_log(test_run_id)


@router.post("/tests/model-features/invoke", response_model=ModelFeatureInvokeResponse)
def invoke_model_feature_test_route(
    request: Request,
    payload: ModelFeatureInvokeRequest,
) -> ModelFeatureInvokeResponse:
    return invoke_model_feature_test(request, payload)


@router.post("/tests/model-features/{feature_id}/invoke", response_model=ModelFeatureInvokeResponse)
def invoke_model_feature_test_route_by_path(
    feature_id: str,
    request: Request,
    payload: dict,
) -> ModelFeatureInvokeResponse:
    base_context = payload.get("base_context") or {}
    injection = payload.get("injection") or {}
    if not isinstance(base_context, dict) or not isinstance(injection, dict):
        raise HTTPException(status_code=422, detail="base_context and injection must be JSON objects")
    return invoke_model_feature_test(
        request,
        ModelFeatureInvokeRequest(
            feature_id=feature_id,
            prompt=str(injection.get("prompt") or "Return a JSON object"),
            context={
                **base_context,
                **injection,
            },
            caller_context={
                "source_module": "zentex.web_console.model_feature_tests",
                "invocation_phase": "manual_test_page",
            },
        ),
    )
