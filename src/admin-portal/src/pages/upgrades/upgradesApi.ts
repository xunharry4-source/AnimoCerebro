/**
 * API contracts and fetch helpers for upgrade management pages.
 *
 * This module keeps LLM and plugin evolution management payloads in one place
 * so the page components can focus on rendering instead of duplicating fetch
 * and response parsing logic.
 */
export type UpgradeLifecycle =
  | "all"
  | "waiting"
  | "ongoing"
  | "completed"
  | "failed"
  | "cancelled";

export type UpgradeTargetKind = "llm" | "plugin";

export interface UpgradeCountSummary {
  all: number;
  waiting: number;
  ongoing: number;
  completed: number;
  failed: number;
  cancelled: number;
}

export interface UpgradeRecordItem {
  record_id: string;
  target_kind: string;
  action: string;
  target_id: string;
  title: string;
  reason: string;
  trace_id: string;
  request_id: string;
  source_event_id?: string | null;
  parent_record_id?: string | null;
  evidence_refs: string[];
  change_summary: string;
  function_summary: string;
  previous_version?: string | null;
  current_version: string;
  candidate_version?: string | null;
  current_status: string;
  lifecycle_view: string;
  current_progress: number;
  success_stage?: string | null;
  success_summary?: string | null;
  reusable_insight?: string | null;
  successful_command?: string | null;
  success_artifact_refs: string[];
  promotion_hint?: string | null;
  success_tags: string[];
  failure_reason?: string | null;
  failure_stage?: string | null;
  failure_code?: string | null;
  failure_summary?: string | null;
  root_cause_hypothesis?: string | null;
  failed_command?: string | null;
  failed_artifact_refs: string[];
  retryable?: boolean | null;
  prevention_hint?: string | null;
  learning_tags: string[];
  source_path?: string | null;
  candidate_path?: string | null;
  audit_status: string;
  memory_status: string;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  can_cancel: boolean;
  can_cleanup_failed_candidate: boolean;
}

export interface UpgradeAuditEventItem {
  event_id: string;
  record_id: string;
  trace_id: string;
  request_id: string;
  source_event_id?: string | null;
  parent_record_id?: string | null;
  target_kind: string;
  action: string;
  target_id: string;
  title: string;
  event_type: string;
  reason: string;
  summary: string;
  current_status: string;
  current_progress: number;
  previous_version?: string | null;
  current_version: string;
  candidate_version?: string | null;
  success_stage?: string | null;
  success_summary?: string | null;
  reusable_insight?: string | null;
  successful_command?: string | null;
  success_artifact_refs: string[];
  promotion_hint?: string | null;
  success_tags: string[];
  failure_reason?: string | null;
  failure_stage?: string | null;
  failure_code?: string | null;
  failure_summary?: string | null;
  root_cause_hypothesis?: string | null;
  failed_command?: string | null;
  failed_artifact_refs: string[];
  retryable?: boolean | null;
  prevention_hint?: string | null;
  learning_tags: string[];
  source_path?: string | null;
  candidate_path?: string | null;
  evidence_refs: string[];
  payload: Record<string, unknown>;
  created_at: string;
}

export interface UpgradeMemoryRecordItem {
  memory_id: string;
  record_id: string;
  trace_id: string;
  request_id: string;
  source_event_id?: string | null;
  parent_record_id?: string | null;
  target_kind: string;
  action: string;
  target_id: string;
  title: string;
  memory_kind: string;
  event_type: string;
  summary: string;
  current_status: string;
  current_progress: number;
  previous_version?: string | null;
  current_version: string;
  candidate_version?: string | null;
  success_stage?: string | null;
  success_summary?: string | null;
  reusable_insight?: string | null;
  successful_command?: string | null;
  success_artifact_refs: string[];
  promotion_hint?: string | null;
  success_tags: string[];
  failure_reason?: string | null;
  failure_stage?: string | null;
  failure_code?: string | null;
  failure_summary?: string | null;
  root_cause_hypothesis?: string | null;
  failed_command?: string | null;
  failed_artifact_refs: string[];
  retryable?: boolean | null;
  prevention_hint?: string | null;
  learning_tags: string[];
  evidence_refs: string[];
  payload: Record<string, unknown>;
  created_at: string;
}

export interface UpgradeRecordCollection {
  target_kind: string;
  lifecycle: string;
  action_filter?: string | null;
  counts: UpgradeCountSummary;
  items: UpgradeRecordItem[];
}

export interface UpgradeOverviewPayload {
  llm: UpgradeCountSummary;
  plugins: UpgradeCountSummary;
  recent_llm: UpgradeRecordItem[];
  recent_plugins: UpgradeRecordItem[];
}

async function readResponseBody(resp: Response): Promise<any> {
  const raw = await resp.text();
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw);
  } catch {
    return { detail: raw };
  }
}

function toErrorMessage(data: any, fallback: string): string {
  if (typeof data?.detail === "string" && data.detail.trim()) {
    return data.detail;
  }
  if (typeof data?.detail?.user_message === "string" && data.detail.user_message.trim()) {
    return data.detail.user_message;
  }
  return fallback;
}

export async function fetchUpgradeOverview(): Promise<UpgradeOverviewPayload> {
  const resp = await fetch("/api/web/upgrades/overview", {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    throw new Error(toErrorMessage(data, `升级总览加载失败（HTTP ${resp.status}）`));
  }
  return data as UpgradeOverviewPayload;
}

export async function fetchUpgradeCollection(
  target: UpgradeTargetKind,
  lifecycle: UpgradeLifecycle,
  action?: string,
): Promise<UpgradeRecordCollection> {
  const params = new URLSearchParams({ lifecycle });
  if (target === "plugin" && action && action !== "all") {
    params.set("action", action);
  }
  const resp = await fetch(`/api/web/upgrades/${target === "llm" ? "llm" : "plugins"}?${params.toString()}`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    throw new Error(toErrorMessage(data, `升级列表加载失败（HTTP ${resp.status}）`));
  }
  return data as UpgradeRecordCollection;
}

export async function fetchUpgradeRecord(recordId: string): Promise<UpgradeRecordItem> {
  const resp = await fetch(`/api/web/upgrades/${recordId}`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    throw new Error(toErrorMessage(data, `升级详情加载失败（HTTP ${resp.status}）`));
  }
  return data as UpgradeRecordItem;
}

export async function fetchUpgradeAuditEvents(
  recordId: string,
): Promise<UpgradeAuditEventItem[]> {
  const resp = await fetch(`/api/web/upgrades/${recordId}/audit-events`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    throw new Error(toErrorMessage(data, `升级审计记录加载失败（HTTP ${resp.status}）`));
  }
  return data as UpgradeAuditEventItem[];
}

export async function fetchUpgradeMemoryRecords(
  recordId: string,
): Promise<UpgradeMemoryRecordItem[]> {
  const resp = await fetch(`/api/web/upgrades/${recordId}/memory-records`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    throw new Error(toErrorMessage(data, `升级记忆记录加载失败（HTTP ${resp.status}）`));
  }
  return data as UpgradeMemoryRecordItem[];
}

export async function cancelUpgradeRecord(
  recordId: string,
  reason: string,
): Promise<UpgradeRecordItem> {
  const resp = await fetch(`/api/web/upgrades/${recordId}/cancel`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ reason }),
  });
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    throw new Error(toErrorMessage(data, `取消升级失败（HTTP ${resp.status}）`));
  }
  return data as UpgradeRecordItem;
}

export async function cleanupFailedCandidate(
  recordId: string,
  reason: string,
): Promise<UpgradeRecordItem> {
  const resp = await fetch(`/api/web/upgrades/${recordId}/cleanup-failed-candidate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ reason }),
  });
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    throw new Error(toErrorMessage(data, `清理失败候选版本失败（HTTP ${resp.status}）`));
  }
  return data as UpgradeRecordItem;
}

/**
 * Response payload for upgrades grouped by lifecycle view.
 */
export interface LifecycleGroupedRecords {
  count: number;
  items: UpgradeRecordItem[];
}

export interface UpgradesByLifecycleViewPayload {
  ongoing: LifecycleGroupedRecords;
  waiting: LifecycleGroupedRecords;
  failed: LifecycleGroupedRecords;
  cancelled: LifecycleGroupedRecords;
  completed: LifecycleGroupedRecords;
}

/**
 * Fetch upgrades grouped by lifecycle view for tabbed display.
 */
export async function fetchUpgradesByLifecycleView(
  targetKind?: UpgradeTargetKind,
  pluginAction?: "all" | "upgrade" | "create",
): Promise<UpgradesByLifecycleViewPayload> {
  const params = new URLSearchParams();
  if (targetKind) {
    params.set("target_kind", targetKind);
  }
  if (pluginAction && pluginAction !== "all") {
    params.set("plugin_action", pluginAction);
  }
  
  const queryString = params.toString();
  const url = `/api/web/upgrades/by-lifecycle-view${queryString ? `?${queryString}` : ""}`;
  
  const resp = await fetch(url, {
    headers: {
      Accept: "application/json",
    },
  });
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    throw new Error(toErrorMessage(data, `获取升级分组数据失败（HTTP ${resp.status}）`));
  }
  return data as UpgradesByLifecycleViewPayload;
}
