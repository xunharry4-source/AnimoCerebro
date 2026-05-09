/**
 * Workspaces API Types and Client
 */

export interface WorkspaceConfig {
  id?: number;
  name: string;
  path: string;
  description?: string;
  is_default?: boolean;
  forbidden_actions?: string;
  task_goals?: string;  // JSON array as string
  created_at?: string;
  updated_at?: string;
}

export interface WorkspaceListResponse {
  workspaces: WorkspaceConfig[];
  total: number;
}

export interface WorkspaceActionResponse {
  success: boolean;
  message: string;
  workspace?: WorkspaceConfig;
}
