export type OverviewPayload = {
  runtime: {
    runtime_id: string;
    active_session_ids: string[];
    transcript_store_status: string;
    memory_store_status: string;
    degraded_mode: boolean;
    manual_confirmation_required: boolean;
  };
  session: {
    session_id: string;
    turn_count?: number;
    active_goal_titles?: string[];
    current_focus_summary?: string | null;
    current_reasoning_mode?: string | null;
    degraded_flags?: string[];
  } | null;
  working_memory: {
    active_focus_titles?: string[];
    current_focus_summary?: string | null;
    slots?: unknown[];
  };
  metacognition: {
    scheduler_status?: string;
    current_reasoning_mode?: string;
  };
  living_self_model: {
    load_level?: string;
    reasoning_posture?: string;
  };
  temporal_agenda: {
    review_now_item_titles?: string[];
    overdue_item_titles?: string[];
  };
  recent_events?: TranscriptEvent[];
};

export type TranscriptEvent = {
  entry_id: string;
  session_id: string;
  turn_id: string;
  entry_type: string;
  timestamp: string;
  source: string;
  trace_id: string;
  payload: unknown;
};

export type CognitivePluginRow = {
  tool_id: string;
  plugin_kind: string;
  status: "candidate" | "sandbox_verified" | "active" | "degraded" | "revoked";
  health_status: string | null;
  usage_count: number;
  failure_count: number;
  rollback_conditions: string[];
  trigger_conditions: string[];
};

export type CognitiveConflict = {
  conflict_id: string;
  conflict_type: string;
  severity: "low" | "medium" | "high" | "critical";
  suggested_resolution: string;
  source_plugin_id: string;
  status: "unresolved" | "reconciling" | "resolved";
};

export type InteractionMindState = {
  entity_id: string;
  brain_scope: string;
  snapshot_version: number;
  clarification_mode: boolean;
  model: {
    role_hint: string;
    current_goal_hypothesis: string;
    knowledge_depth: "low" | "medium" | "high";
  };
  communication_fit: {
    preferred_style: "brief" | "structured" | "evidence_first" | "conclusion_first";
    risk_of_misunderstanding: number;
  };
  misunderstanding_signals: Array<{
    signal_id: string;
    signal_type: string;
    severity: "low" | "medium" | "high" | "critical";
  }>;
};
