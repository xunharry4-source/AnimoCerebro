export type PluginRow = {
  tool_id: string;
  feature_code: string;
  supports_multiple_plugins: boolean;
  plugin_kind: string;
  version: string;
  status: "candidate" | "active" | "degraded" | "revoked" | "sandbox_verified";
  health_status: string | null;
  purpose: string;
  description: string;
  used_in: string[];
  is_default: boolean;
  is_official_release: boolean;
  can_force_enable: boolean;
  can_force_disable: boolean;
  can_delete: boolean;
  usage_count: number;
  failure_count: number;
  rollback_conditions: string[];
  trigger_conditions: string[];
  required_context: string[];
  created_at: string | null;
  updated_at: string | null;
  started_at: string | null;
  stopped_at: string | null;
  last_used_at: string | null;
};

export type PluginHistoryItem = {
  plugin_id: string;
  version: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  previous_version: string | null;
};

export type PluginRelationshipItem = {
  plugin: PluginRow;
  role: string;
  priority: number;
  fallback_id: string | null;
  relationship_created_at: string | null;
  relationship_updated_at: string | null;
};

export type CognitivePluginDetailResponse = {
  plugin: PluginRow;
  functional_plugins: PluginRelationshipItem[];
  history: PluginHistoryItem[];
};

export type FunctionalPluginDetailResponse = {
  plugin: PluginRow;
  cognitive_plugins: PluginRelationshipItem[];
  history: PluginHistoryItem[];
};

export type PluginRelationActionRequest = {
  audit_reason: string;
  role?: string;
  priority?: number;
  fallback_id?: string | null;
};

export type PluginTestRequest = {
  audit_reason: string;
  idempotency_key: string;
};

export type ForceEnableResponse = {
  plugin: PluginRow;
  auto_disabled_plugin_ids: string[];
  requires_override_warning: boolean;
  message: string;
};

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `request_failed_${response.status}`);
  }
  return (await response.json()) as T;
}

export function fetchCognitivePlugins(): Promise<PluginRow[]> {
  return requestJson<PluginRow[]>("/api/web/plugins/cognitive");
}

export function fetchFunctionalPlugins(): Promise<PluginRow[]> {
  return requestJson<PluginRow[]>("/api/web/plugins/functional");
}

export function fetchCognitivePluginDetail(pluginId: string): Promise<CognitivePluginDetailResponse> {
  return requestJson<CognitivePluginDetailResponse>(`/api/web/plugins/cognitive/${encodeURIComponent(pluginId)}`);
}

export function fetchFunctionalPluginDetail(pluginId: string): Promise<FunctionalPluginDetailResponse> {
  return requestJson<FunctionalPluginDetailResponse>(`/api/web/plugins/functional/${encodeURIComponent(pluginId)}`);
}

export function fetchPluginHistory(pluginId: string): Promise<PluginHistoryItem[]> {
  return requestJson<PluginHistoryItem[]>(`/api/web/plugins/${encodeURIComponent(pluginId)}/history`);
}

export function bindFunctionalPlugin(
  cognitivePluginId: string,
  functionalPluginId: string,
  payload: PluginRelationActionRequest,
): Promise<CognitivePluginDetailResponse> {
  return requestJson<CognitivePluginDetailResponse>(
    `/api/web/plugins/cognitive/${encodeURIComponent(cognitivePluginId)}/functional/${encodeURIComponent(functionalPluginId)}/bind`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

export function unbindFunctionalPlugin(
  cognitivePluginId: string,
  functionalPluginId: string,
  payload: PluginRelationActionRequest,
): Promise<CognitivePluginDetailResponse> {
  return requestJson<CognitivePluginDetailResponse>(
    `/api/web/plugins/cognitive/${encodeURIComponent(cognitivePluginId)}/functional/${encodeURIComponent(functionalPluginId)}/bind`,
    {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

export function testFunctionalPlugin(
  cognitivePluginId: string,
  functionalPluginId: string,
  payload: PluginTestRequest,
): Promise<{ plugin_id: string; ok: boolean; details: Record<string, unknown> }> {
  return requestJson<{ plugin_id: string; ok: boolean; details: Record<string, unknown> }>(
    `/api/web/plugins/cognitive/${encodeURIComponent(cognitivePluginId)}/functional/${encodeURIComponent(functionalPluginId)}/test`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

export function forceEnablePlugin(pluginId: string, auditReason: string): Promise<ForceEnableResponse> {
  return requestJson<ForceEnableResponse>(`/api/web/plugins/${encodeURIComponent(pluginId)}/force-enable`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ audit_reason: auditReason }),
  });
}

export function forceDisablePlugin(pluginId: string, auditReason: string): Promise<PluginRow> {
  return requestJson<PluginRow>(`/api/web/plugins/${encodeURIComponent(pluginId)}/force-disable`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ audit_reason: auditReason }),
  });
}

export function deletePlugin(pluginId: string, auditReason: string): Promise<{ deleted_plugin_id: string }> {
  return requestJson<{ deleted_plugin_id: string }>(`/api/web/plugins/${encodeURIComponent(pluginId)}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ audit_reason: auditReason }),
  });
}
