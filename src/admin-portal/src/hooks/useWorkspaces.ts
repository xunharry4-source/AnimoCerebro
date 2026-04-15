import { useCallback, useEffect, useState } from "react";
import { WorkspaceConfig, WorkspaceListResponse, WorkspaceActionResponse } from "../../../api/workspacesApi";

const API_BASE = "http://127.0.0.1:8000/api/web/workspaces";

/**
 * Hook for managing workspaces
 */
export function useWorkspaces() {
  const [workspaces, setWorkspaces] = useState<WorkspaceConfig[]>([]);
  const [currentWorkspaceId, setCurrentWorkspaceId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load current workspace from localStorage on mount
  useEffect(() => {
    const savedId = localStorage.getItem("currentWorkspaceId");
    if (savedId) {
      setCurrentWorkspaceId(parseInt(savedId, 10));
    }
  }, []);

  // Fetch workspaces list
  const fetchWorkspaces = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/`);
      if (!response.ok) throw new Error("Failed to fetch workspaces");
      const data: WorkspaceListResponse = await response.json();
      setWorkspaces(data.workspaces);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  // Add workspace
  const addWorkspace = useCallback(
    async (config: Omit<WorkspaceConfig, "id" | "created_at" | "updated_at">) => {
      try {
        const response = await fetch(`${API_BASE}/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(config),
        });
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || "Failed to create workspace");
        }
        const data: WorkspaceActionResponse = await response.json();
        if (data.workspace) {
          setWorkspaces((prev) => [...prev, data.workspace!]);
        }
        return data;
      } catch (err) {
        throw err;
      }
    },
    []
  );

  // Update workspace
  const updateWorkspace = useCallback(
    async (id: number, config: Omit<WorkspaceConfig, "id" | "created_at" | "updated_at">) => {
      try {
        const response = await fetch(`${API_BASE}/${id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(config),
        });
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || "Failed to update workspace");
        }
        const data: WorkspaceActionResponse = await response.json();
        if (data.workspace) {
          setWorkspaces((prev) =>
            prev.map((w) => (w.id === id ? data.workspace! : w))
          );
        }
        return data;
      } catch (err) {
        throw err;
      }
    },
    []
  );

  // Delete workspace
  const deleteWorkspace = useCallback(async (id: number) => {
    try {
      const response = await fetch(`${API_BASE}/${id}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to delete workspace");
      }
      const data: WorkspaceActionResponse = await response.json();
      setWorkspaces((prev) => prev.filter((w) => w.id !== id));
      return data;
    } catch (err) {
      throw err;
    }
  }, []);

  // Set default workspace
  const setDefaultWorkspace = useCallback(async (id: number) => {
    try {
      const response = await fetch(`${API_BASE}/${id}/set-default`, {
        method: "POST",
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to set default workspace");
      }
      const data: WorkspaceActionResponse = await response.json();
      if (data.workspace) {
        setWorkspaces((prev) =>
          prev.map((w) => ({
            ...w,
            is_default: w.id === id,
          }))
        );
      }
      return data;
    } catch (err) {
      throw err;
    }
  }, []);

  // Set current workspace in local storage
  const selectWorkspace = useCallback((id: number) => {
    setCurrentWorkspaceId(id);
    localStorage.setItem("currentWorkspaceId", id.toString());
  }, []);

  // Set current workspace (in runtime session)
  const setCurrentWorkspace = useCallback(async (id: number) => {
    try {
      const response = await fetch(`${API_BASE}/${id}/set-current`, {
        method: "POST",
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to set current workspace");
      }
      selectWorkspace(id);
      return await response.json();
    } catch (err) {
      throw err;
    }
  }, [selectWorkspace]);

  return {
    workspaces,
    currentWorkspaceId,
    loading,
    error,
    fetchWorkspaces,
    addWorkspace,
    updateWorkspace,
    deleteWorkspace,
    setDefaultWorkspace,
    setCurrentWorkspace,
    selectWorkspace,
  };
}
