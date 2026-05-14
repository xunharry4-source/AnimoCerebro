// Task Management Type Definitions

export type TaskStatus = 
  | 'todo' 
  | 'assignment_pending'
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
  contract?: Record<string, any>;
  metadata?: Record<string, any>;
  subtask_count?: number;
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
  suspension?: {
    task_id: string;
    original_status: string;
    suspension_reason: string;
    recovery_conditions?: string[];
    suspension_context?: Record<string, any>;
    suspended_at?: string;
    auto_resume_at?: string | null;
  };
}

export interface TasksByStatus {
  all?: ZentexTask[];
  in_progress: ZentexTask[];
  todo?: ZentexTask[];
  blocked?: ZentexTask[];
  pending: ZentexTask[];
  waiting_confirmation: ZentexTask[];
  completed: ZentexTask[];
  failed?: ZentexTask[];
  suspended?: ZentexTask[];
  archived?: ZentexTask[];
  cancelled: ZentexTask[];
}

export type TaskPresentationGroup =
  | 'all'
  | 'in_progress'
  | 'todo'
  | 'blocked'
  | 'pending'
  | 'waiting_confirmation'
  | 'completed'
  | 'failed'
  | 'suspended'
  | 'archived'
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

export interface TaskGarbageDuplicateGroup {
  group_id: string;
  group_kind: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | string;
  signature: string;
  reason: string;
  recommended_action: string;
  task_ids: string[];
  task_count: number;
  titles: string[];
  source_module: string;
  statuses: string[];
}

export interface TaskGarbageCandidate {
  task_id: string;
  title: string;
  status: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | string;
  issue_type: string;
  reason: string;
  recommended_action: string;
  source_module: string;
  parent_task_id?: string | null;
  age_seconds?: number;
}

export interface TaskGarbageAssessment {
  task_id: string;
  rule_based_flags: {
    is_idempotency_duplicate: boolean;
    is_orphan_or_stale: boolean;
    is_dependency_deadlock: boolean;
    is_retry_budget_exhausted?: boolean;
  };
  rule_based_score: number;
  llm_semantic_evaluation: {
    status: string;
    semantic_duplicate_score: number | null;
    garbage_noise_score: number | null;
    comprehensive_value_score: number | null;
    evaluation_reason: string;
    target_merge_task_id?: string | null;
    final_decision?: string;
  };
  final_decision: string;
  target_merge_task_id?: string | null;
  duplicate_group_ids: string[];
  garbage_issue_types: string[];
}

export interface TaskGarbageAnalysisReport {
  report_id: string;
  generated_at: string;
  stale_after_seconds: number;
  summary: {
    total_tasks: number;
    active_tasks: number;
    q9_task_count: number;
    duplicate_group_count: number;
    garbage_candidate_count: number;
    high_risk_count: number;
  };
  source_counts: Record<string, number>;
  duplicate_groups: TaskGarbageDuplicateGroup[];
  garbage_candidates: TaskGarbageCandidate[];
  task_assessments: TaskGarbageAssessment[];
  llm_semantic_scoring: {
    enabled: boolean;
    mandatory_for_semantic_decisions: boolean;
    evaluated_group_count: number;
    unavailable_group_count: number;
  };
  execution_plan: {
    auto_execution_enabled: boolean;
    reason: string;
    candidate_action_count: number;
  };
}

export interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}
