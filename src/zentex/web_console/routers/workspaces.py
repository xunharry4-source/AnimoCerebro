"""
Workspaces API Routes / 工作区 API 路由

FastAPI routes for workspace management.
工作区管理的 FastAPI 路由。
"""

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status, Request
from typing_extensions import Annotated
from fastapi import Depends

from zentex.web_console.models.workspace import (
    WorkspaceConfig,
    WorkspaceListResponse,
    WorkspaceActionResponse,
)
from zentex.web_console.dependencies import get_kernel_service_facade
from zentex.kernel.workspace_store import WorkspaceStore
from zentex.web_console.dependencies import get_workspace_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _validate_path(path: str) -> None:
    """
    Validate workspace path.
    
    Args:
        path: Path to validate
        
    Raises:
        ValueError: If path is invalid or inaccessible
    """
    try:
        p = Path(path).resolve()
        
        # Check if path exists
        if not p.exists():
            raise ValueError(f"Path does not exist: {path}")
        
        # Check if it's a directory
        if not p.is_dir():
            raise ValueError(f"Path is not a directory: {path}")
        
        # Check if readable
        if not os.access(p, os.R_OK):
            raise ValueError(f"Path is not readable: {path}")
        
        # Reject system paths
        forbidden_prefixes = [
            "/etc", "/sys", "/proc", "/dev", "/boot",
            "C:\\Windows", "C:\\System32", "C:\\Program Files"
        ]
        path_str = str(p).lower()
        for prefix in forbidden_prefixes:
            if path_str.startswith(prefix.lower()):
                raise ValueError(f"Cannot add system path: {path}")
                
    except (OSError, ValueError) as e:
        raise ValueError(str(e))


@router.get("/", response_model=WorkspaceListResponse)
def list_workspaces(
    store: Annotated[WorkspaceStore, Depends(get_workspace_store)]
) -> WorkspaceListResponse:
    """
    Get all workspaces.
    
    获取所有工作区。
    """
    try:
        workspaces = store.list_workspaces()
        return WorkspaceListResponse(workspaces=workspaces, total=len(workspaces))
    except Exception as e:
        logger.error(f"Error listing workspaces: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list workspaces"
        )


@router.get("/{workspace_id}", response_model=WorkspaceConfig)
def get_workspace(
    workspace_id: int,
    store: Annotated[WorkspaceStore, Depends(get_workspace_store)]
) -> WorkspaceConfig:
    """
    Get a specific workspace.
    
    获取单个工作区。
    """
    try:
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workspace {workspace_id} not found"
            )
        return workspace
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workspace: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get workspace"
        )


@router.post("/", response_model=WorkspaceActionResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(
    config: WorkspaceConfig,
    store: Annotated[WorkspaceStore, Depends(get_workspace_store)]
) -> WorkspaceActionResponse:
    """
    Create a new workspace.
    
    创建新工作区。
    """
    try:
        # Validate path
        _validate_path(config.path)
        
        # Add workspace
        created = store.add_workspace(config)
        return WorkspaceActionResponse(
            success=True,
            message=f"Workspace '{created.name}' created successfully",
            workspace=created
        )
    except ValueError as e:
        logger.warning(f"Validation error creating workspace: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating workspace: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create workspace"
        )


@router.put("/{workspace_id}", response_model=WorkspaceActionResponse)
def update_workspace(
    workspace_id: int,
    config: WorkspaceConfig,
    store: Annotated[WorkspaceStore, Depends(get_workspace_store)]
) -> WorkspaceActionResponse:
    """
    Update an existing workspace.
    
    更新工作区。
    """
    try:
        # Validate path
        _validate_path(config.path)
        
        # Update workspace
        updated = store.update_workspace(workspace_id, config)
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workspace {workspace_id} not found"
            )
        
        return WorkspaceActionResponse(
            success=True,
            message=f"Workspace '{updated.name}' updated successfully",
            workspace=updated
        )
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Validation error updating workspace: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating workspace: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update workspace"
        )


@router.delete("/{workspace_id}", response_model=WorkspaceActionResponse)
def delete_workspace(
    workspace_id: int,
    store: Annotated[WorkspaceStore, Depends(get_workspace_store)]
) -> WorkspaceActionResponse:
    """
    Delete a workspace.
    
    删除工作区。
    """
    try:
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workspace {workspace_id} not found"
            )
        
        deleted = store.delete_workspace(workspace_id)
        if deleted:
            return WorkspaceActionResponse(
                success=True,
                message=f"Workspace '{workspace.name}' deleted successfully"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete workspace"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting workspace: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete workspace"
        )


@router.post("/{workspace_id}/set-default", response_model=WorkspaceActionResponse)
def set_default_workspace(
    workspace_id: int,
    store: Annotated[WorkspaceStore, Depends(get_workspace_store)]
) -> WorkspaceActionResponse:
    """
    Set a workspace as default.
    
    设置工作区为默认。
    """
    try:
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workspace {workspace_id} not found"
            )
        
        success = store.set_default_workspace(workspace_id)
        if success:
            return WorkspaceActionResponse(
                success=True,
                message=f"Workspace '{workspace.name}' set as default",
                workspace=store.get_workspace(workspace_id)
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set default workspace"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting default workspace: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set default workspace"
        )


@router.get("/default/info", response_model=WorkspaceConfig)
def get_default_workspace(
    store: Annotated[WorkspaceStore, Depends(get_workspace_store)]
) -> WorkspaceConfig:
    """
    Get the default workspace.
    
    获取默认工作区。
    """
    try:
        workspace = store.get_default_workspace()
        if not workspace:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No default workspace configured"
            )
        return workspace
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting default workspace: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get default workspace"
        )


@router.post("/{workspace_id}/set-current", response_model=WorkspaceActionResponse)
async def set_current_workspace(
    workspace_id: int,
    store: Annotated[WorkspaceStore, Depends(get_workspace_store)],
    request: Request,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> WorkspaceActionResponse:
    """
    Set the current workspace for the active runtime session.
    
    设置当前会话的工作区。
    """
    try:
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workspace {workspace_id} not found"
            )
        
        # Try to persist the workspace onto the active session snapshot if available.
        try:
            session_manager = facade.get_session_manager()
            active_session = getattr(request.app.state, "session", None)
            session_id = getattr(active_session, "session_id", None)
            if session_id:
                await session_manager.update_session_state(session_id, workspace=workspace.path)
        except Exception:
            # Session might not be available, that's ok
            pass
        
        return WorkspaceActionResponse(
            success=True,
            message=f"Current workspace set to '{workspace.name}'",
            workspace=workspace
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting current workspace: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set current workspace"
        )
