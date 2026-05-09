from __future__ import annotations

"""System identity API routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from zentex.web_console.contracts.kernel_service import KernelServiceFacade
from zentex.web_console.dependencies import get_kernel_service_facade
from zentex.web_console.models.system_identity import (
    SystemIdentityConfig,
    SystemIdentityResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system-identity", tags=["system-identity"])


@router.get("/", response_model=SystemIdentityResponse)
def get_system_identity(
    facade: Annotated[KernelServiceFacade, Depends(get_kernel_service_facade)],
) -> SystemIdentityResponse:
    """Return the single system role used by Q2 and later 9Q processing."""
    return SystemIdentityResponse.model_validate(facade.get_system_identity())


@router.put("/", response_model=SystemIdentityResponse)
def update_system_identity(
    config: SystemIdentityConfig,
    facade: Annotated[KernelServiceFacade, Depends(get_kernel_service_facade)],
) -> SystemIdentityResponse:
    """Create or replace the single system role used by Q2."""
    try:
        return SystemIdentityResponse.model_validate(
            facade.update_system_identity(
                role_name=config.role_name,
                mission=config.mission,
                core_values=config.core_values,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed updating system identity")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.delete("/", response_model=SystemIdentityResponse)
def reset_system_identity(
    facade: Annotated[KernelServiceFacade, Depends(get_kernel_service_facade)],
) -> SystemIdentityResponse:
    """Clear the user-configured system role."""
    return SystemIdentityResponse.model_validate(facade.reset_system_identity())
