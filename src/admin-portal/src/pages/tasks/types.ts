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
}

export interface TasksByStatus {
  in_progress: ZentexTask[];
  pending: ZentexTask[];
  waiting_confirmation: ZentexTask[];
  completed: ZentexTask[];
  cancelled: ZentexTask[];
}

export interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}
