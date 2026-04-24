export interface AuditGraphNodeView {
  node_id: string;
  title: string;
  lane: string;
  status: string;
  description: string;
  href?: string | null;
  metrics: Record<string, any>;
}

export interface AuditGraphEdgeView {
  edge_id: string;
  source: string;
  target: string;
  label: string;
}

export interface AuditGraphLaneView {
  lane_id: string;
  title: string;
  subtitle: string;
  nodes: AuditGraphNodeView[];
}

export interface AuditGraphPayloadView {
  mode: string;
  title: string;
  subtitle: string;
  database_backed: boolean;
  generated_at: string;
  summary: Record<string, any>;
  lanes: AuditGraphLaneView[];
  edges: AuditGraphEdgeView[];
}

export async function fetchAuditTraceGraph(mode: string): Promise<AuditGraphPayloadView> {
  const response = await fetch(`/api/web/audit/trace-center/${encodeURIComponent(mode)}`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail =
      (typeof data?.detail === "string" && data.detail) ||
      (typeof data?.detail?.message === "string" && data.detail.message) ||
      `获取审计工作流失败（HTTP ${response.status}）`;
    throw new Error(detail);
  }
  return data as AuditGraphPayloadView;
}
