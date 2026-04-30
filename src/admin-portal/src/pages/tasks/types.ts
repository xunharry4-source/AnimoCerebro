// Task Management Type Definitions

export type TaskStatus = 
  | 'todo' 
  | 'in_progress' 
  | 'blocked' 
  | 'waiting_confirmation' 
  | 'done' 
  | 'failed' 
  | 'suspended' 
  | 'archived'
  | 'cancelled'; // Add cancelled

export interface ZentexTask {
  id: string; // Required for DataGrid
  task_id: string;
  parent_task_id?: string;
  subtask_ids?: string[];
  depends_on?: string[];
  subtask_id: string;
  idempotency_key: string;
  title: string;
  task_type: string;
  task_scope?: 'internal' | 'external' | string;
  status: TaskStatus;
  priority?: string;
  progress: number;
  originator_id: string;
  target_id?: string;
  remarks: string | null;
  started_at: string | null;
  completed_at?: string | null; // Make optional
  created_at?: string;
  deadline?: string;
  tags?: string[];
  metadata?: Record<string, any>;
  attempt_count?: number;
  last_error?: string | null;
  execution_started_at?: string | null;
  execution_finished_at?: string | null;
  dispatch_plugin_id?: string | null;
  execution_output?: string | null;
  execution_assignment?: {
    status: 'assigned' | 'routed' | 'declared' | 'pending_dispatch' | 'dispatch_blocked' | 'unassigned' | string;
    source: string;
    executor_id: string;
    executor_type: string;
    label: string;
  };
}

export interface TasksByStatus {
  in_progress: ZentexTask[];
  todo?: ZentexTask[];
  blocked?: ZentexTask[];
  pending: ZentexTask[];
  waiting_confirmation: ZentexTask[];
  completed: ZentexTask[];
  cancelled: ZentexTask[];
}

export type TaskPresentationGroup =
  | 'in_progress'
  | 'todo'
  | 'blocked'
  | 'pending'
  | 'waiting_confirmation'
  | 'completed'
  | 'cancelled';

export type TaskGroupCounts = Record<TaskPresentationGroup, number>;

export interface TaskPageResponse {
  group: TaskPresentationGroup;
  items: ZentexTask[];
  total: number;
  limit: number;
  offset: number;
  counts: TaskGroupCounts;
}

export interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}
