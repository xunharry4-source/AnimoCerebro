import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  Divider,
  Stack,
  Typography,
} from "@mui/material";

type WorkflowModulePayload = Record<string, any>;

const WORKFLOW_ORDER = [
  "dependency_check",
  "functional_plugin_chain",
  "environment_service",
  "environment_scan",
  "workspace_structure_scan",
  "content_sampling",
  "domain_inference",
  "state_write",
] as const;

const WORKFLOW_LABELS: Record<string, string> = {
  dependency_check: "依赖检查",
  functional_plugin_chain: "功能插件链",
  environment_service: "环境服务",
  environment_scan: "环境扫描",
  workspace_structure_scan: "工作区结构扫描",
  content_sampling: "内容采样",
  domain_inference: "领域推断",
  state_write: "状态写入",
};

function statusColor(status: string): "default" | "success" | "warning" | "error" | "info" {
  if (status === "ready" || status === "completed") return "success";
  if (status === "degraded" || status === "partial" || status === "running") return "warning";
  if (status === "failed") return "error";
  if (status === "missing" || status === "unavailable" || status === "no_result") return "default";
  return "info";
}

function workflowSummary(moduleId: string, payload: WorkflowModulePayload): string {
  const data = (payload?.data ?? {}) as Record<string, any>;

  if (moduleId === "dependency_check") {
    return `已启用功能插件 ${Number(data.enabled_functional_plugins || 0)} 个`;
  }
  if (moduleId === "functional_plugin_chain") {
    return `链路状态 ${String(data.status || payload?.status || "unknown")}`;
  }
  if (moduleId === "environment_service") {
    return `服务状态 ${String(data.status || payload?.status || "unknown")}`;
  }
  if (moduleId === "environment_scan") {
    return `环境摘要 ${Array.isArray(data.environment_summary) ? data.environment_summary.length : 0} 条`;
  }
  if (moduleId === "workspace_structure_scan") {
    return `顶层目录 ${Array.isArray(data.top_level_dirs) ? data.top_level_dirs.length : 0} 个`;
  }
  if (moduleId === "content_sampling") {
    const sampleCount = Number(data.sample_count || data.sampled_file_summaries?.length || 0);
    const anomalyCount = Number(data.anomaly_count || data.log_anomaly_snippets?.length || 0);
    return `样本 ${sampleCount} 个，异常 ${anomalyCount} 个`;
  }
  if (moduleId === "domain_inference") {
    return data.primary_domain ? `主领域 ${String(data.primary_domain)}` : "等待推断结果";
  }
  if (moduleId === "state_write") {
    return `真实性 ${String(data.overall_authenticity || "unknown")}`;
  }
  return "无结果摘要";
}

export default function Q1WorkflowPanel({
  modules,
  diagnosis,
}: {
  modules: Record<string, WorkflowModulePayload> | null | undefined;
  diagnosis?: Record<string, any> | null;
}) {
  const orderedModules = WORKFLOW_ORDER.map((moduleId) => [moduleId, modules?.[moduleId] || {}] as const);
  const pluginRuns = Array.isArray(diagnosis?.plugin_runs) ? diagnosis?.plugin_runs : [];

  return (
    <Box data-testid="q1-workflow-panel">
      <Typography variant="h6" sx={{ mb: 1, fontWeight: 700 }}>
        Q1 内部工作流
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        以节点流方式展示 Q1 的执行状态与结果，便于定位到底是依赖、采样、推断还是写入阶段出问题。
      </Typography>

      <Stack
        direction={{ xs: "column", lg: "row" }}
        spacing={2}
        useFlexGap
        sx={{ overflowX: { lg: "auto" }, pb: 1 }}
      >
        {orderedModules.map(([moduleId, payload], index) => {
          const moduleStatus = String(payload?.status || "missing");
          const moduleError = String(payload?.error || "");
          return (
            <Stack
              key={moduleId}
              direction={{ xs: "column", lg: "row" }}
              alignItems="stretch"
              spacing={1}
              sx={{ minWidth: { lg: 260 } }}
            >
              <Card
                variant="outlined"
                sx={{
                  flex: 1,
                  minHeight: 196,
                  borderColor: moduleStatus === "failed" ? "error.main" : "divider",
                  background:
                    moduleStatus === "ready"
                      ? "linear-gradient(180deg, rgba(30,136,229,0.06), rgba(255,255,255,0.96))"
                      : moduleStatus === "degraded"
                        ? "linear-gradient(180deg, rgba(245,124,0,0.08), rgba(255,255,255,0.96))"
                        : "linear-gradient(180deg, rgba(0,0,0,0.02), rgba(255,255,255,0.96))",
                }}
              >
                <CardContent>
                  <Stack direction="row" justifyContent="space-between" spacing={1} sx={{ mb: 1 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                      {WORKFLOW_LABELS[moduleId] || moduleId}
                    </Typography>
                    <Chip label={moduleStatus} size="small" color={statusColor(moduleStatus)} />
                  </Stack>
                  <Typography variant="body2" sx={{ mb: 1.5 }}>
                    {workflowSummary(moduleId, payload)}
                  </Typography>
                  {moduleError ? (
                    <Alert severity="error" sx={{ mb: 1 }}>
                      {moduleError}
                    </Alert>
                  ) : null}
                  <Box
                    sx={{
                      p: 1.25,
                      borderRadius: 2,
                      bgcolor: "rgba(15, 23, 42, 0.04)",
                      fontFamily: "monospace",
                      fontSize: 12,
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                    }}
                  >
                    {JSON.stringify(payload?.data ?? {}, null, 2) || "{}"}
                  </Box>
                </CardContent>
              </Card>
              {index < orderedModules.length - 1 ? (
                <Stack alignItems="center" justifyContent="center" sx={{ px: { lg: 0.5 } }}>
                  <Typography variant="h5" color="text.disabled">
                    →
                  </Typography>
                </Stack>
              ) : null}
            </Stack>
          );
        })}
      </Stack>

      <Divider sx={{ my: 2.5 }} />

      <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 700 }}>
        功能插件执行结果
      </Typography>
      {pluginRuns.length === 0 ? (
        <Alert severity="info">当前没有可展示的功能插件执行记录。</Alert>
      ) : (
        <Stack spacing={1.25}>
          {pluginRuns.map((run: Record<string, any>, index: number) => (
            <Card key={`${run.plugin_id || "plugin"}-${index}`} variant="outlined">
              <CardContent sx={{ py: 1.5 }}>
                <Stack direction="row" justifyContent="space-between" spacing={1} sx={{ mb: 0.75 }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                    {String(run.plugin_id || "unknown_plugin")}
                  </Typography>
                  <Chip label={String(run.status || "unknown")} size="small" color={statusColor(String(run.status || ""))} />
                </Stack>
                <Typography variant="body2" color="text.secondary">
                  feature: {String(run.feature_code || "-")}
                </Typography>
                {run.output_summary ? (
                  <Typography variant="body2" sx={{ mt: 0.5 }}>
                    result: {String(run.output_summary)}
                  </Typography>
                ) : null}
                {run.error_message ? (
                  <Typography variant="body2" color="error.main" sx={{ mt: 0.5 }}>
                    error: {String(run.error_message)}
                  </Typography>
                ) : null}
              </CardContent>
            </Card>
          ))}
        </Stack>
      )}
    </Box>
  );
}
