from __future__ import annotations

from pathlib import Path

from zentex.kernel.workspace_store import WorkspaceStore as CoreWorkspaceStore
from zentex.web_console.kernel_service_impl import DefaultKernelServiceFacade
from zentex.web_console.storage.workspace import WorkspaceStore as CompatibilityWorkspaceStore


def test_workspace_store_is_core_managed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ZENTEX_DATA_ROOT", str(tmp_path))

    facade = DefaultKernelServiceFacade()
    store = facade.get_workspace_store()

    assert isinstance(store, CoreWorkspaceStore)
    assert CompatibilityWorkspaceStore is CoreWorkspaceStore
    assert store.db_path == tmp_path / "workspaces.db"
