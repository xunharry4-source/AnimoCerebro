import { Alert, Box, Card, CardContent, Chip, Divider, Grid, Stack, Typography } from "@mui/material";
import {
  LLMTracePayloadView,
  Q3PreprocessedEvidence,
  Q3WhatDoIHaveInferenceView,
} from "../pages/nine-questions/nineQuestionsApi";
import LLMTracePanel from "./LLMTracePanel";

function asRecord(value: unknown): Record<string, any> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, any>) : {};
}

function countKeys(value: unknown): number {
  return Object.keys(asRecord(value)).length;
}

export function Q3EvidencePanel({
  evidence,
  inference,
  providerName,
  elapsedMs = 0,
  trace,
}: {
  evidence: Q3PreprocessedEvidence;
  inference: Q3WhatDoIHaveInferenceView | null | undefined;
  providerName?: string | null;
  elapsedMs?: number;
  trace?: LLMTracePayloadView | null;
}) {
  const role = inference?.role_profile;
  const mission = inference?.mission_boundary;
  const identityKernel = asRecord(evidence.identity_kernel_snapshot);
  const q1Environment = asRecord(evidence.q1_environment_inference);
  const q2Assets = asRecord(evidence.q2_asset_inventory);
  const q1LlmTrace = asRecord(evidence.q1_llm_trace_payload);
  const q2LlmTrace = asRecord(evidence.q2_llm_trace_payload);
  const userLocked = Boolean(identityKernel.user_configured || identityKernel.source === "user_system_identity_store");

  return (
    <Grid container spacing={3} sx={{ mt: 0.5 }}>
      {(providerName || elapsedMs > 0) && (
        <Grid size={{ xs: 12 }}>
          <Box sx={{ display: "flex", gap: 1, mb: 1 }}>
            {providerName && <Chip label={`Role Engine: ${providerName}`} size="small" variant="outlined" color="secondary" />}
            {elapsedMs > 0 && <Chip label={`Latency: ${elapsedMs}ms`} size="small" variant="outlined" />}
          </Box>
        </Grid>
      )}

      <Grid size={{ xs: 12 }}>
        <Card variant="outlined" sx={{ borderColor: "primary.main" }}>
          <CardContent>
            <Typography variant="h6" gutterBottom sx={{ fontWeight: "bold" }}>
              Q3 角色推断结果
            </Typography>
            {role ? (
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Box sx={{ bgcolor: "background.default", p: 2, borderRadius: 1, border: "1px solid", borderColor: "divider" }}>
                    <Typography variant="subtitle2" gutterBottom>RoleProfile</Typography>
                    <Typography variant="body2"><strong>identity_role:</strong> {role.identity_role}</Typography>
                    <Divider sx={{ my: 1 }} />
                    <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
                      <Typography variant="body2"><strong>active_role:</strong> {role.active_role}</Typography>
                      {userLocked ? <Chip size="small" color="warning" label="User Locked" data-testid="q3-user-locked-chip" /> : null}
                    </Stack>
                    <Divider sx={{ my: 1 }} />
                    <Typography variant="body2" color="text.secondary">
                      <strong>inferred_reference_role:</strong> {role.inferred_reference_role || "N/A"}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                      {role.role_alignment_gap || "未检测到角色适配偏差。"}
                    </Typography>
                    <Divider sx={{ my: 1 }} />
                    <Typography variant="body2"><strong>task_role:</strong> {role.task_role}</Typography>
                  </Box>
                </Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Box sx={{ bgcolor: "rgba(25, 118, 210, 0.05)", p: 2, borderRadius: 1, border: "1px solid", borderColor: "primary.light" }}>
                    <Typography variant="subtitle2" gutterBottom>MissionBoundary</Typography>
                    <Typography variant="body2" sx={{ fontWeight: "bold", color: "primary.main" }}>
                      current_mission: {mission?.current_mission || "N/A"}
                    </Typography>
                    <Typography variant="subtitle2" sx={{ mt: 1 }}>priority_duties</Typography>
                    <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap">
                      {(mission?.priority_duties || []).map((item) => (
                        <Chip key={item} label={item} size="small" variant="outlined" color="primary" />
                      ))}
                    </Stack>
                    <Typography variant="subtitle2" sx={{ mt: 1 }}>continuity_boundaries</Typography>
                    <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap">
                      {(mission?.continuity_boundaries || []).map((item) => (
                        <Chip key={item} label={item} size="small" variant="outlined" color="secondary" />
                      ))}
                    </Stack>
                  </Box>
                </Grid>
              </Grid>
            ) : (
              <Alert severity="info">等待 Q3 角色推断结果。</Alert>
            )}
          </CardContent>
        </Card>
      </Grid>

      <Grid size={{ xs: 12 }}>
        <Card variant="outlined">
          <CardContent>
            <Typography variant="h6" gutterBottom>Q3 输入证据</Typography>
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, md: 4 }}>
                <Box sx={{ p: 2, border: "1px solid", borderColor: "divider", borderRadius: 1 }}>
                  <Typography variant="subtitle2">Q1 环境推断</Typography>
                  <Typography variant="body2" color="text.secondary">字段数: {countKeys(q1Environment)}</Typography>
                  <Typography variant="body2">{String(q1Environment.primary_domain || q1Environment.summary || "N/A")}</Typography>
                  <Divider sx={{ my: 1 }} />
                  <Typography variant="caption" color="text.secondary" display="block">Q1 LLM 溯源</Typography>
                  <Typography variant="body2">Provider: {String(q1LlmTrace.provider_name || q1LlmTrace.provider_plugin_id || "N/A")}</Typography>
                  <Typography variant="body2">Invocations: {Array.isArray(q1LlmTrace.invocations) ? q1LlmTrace.invocations.length : 0}</Typography>
                </Box>
              </Grid>
              <Grid size={{ xs: 12, md: 4 }}>
                <Box sx={{ p: 2, border: "1px solid", borderColor: "divider", borderRadius: 1 }}>
                  <Typography variant="subtitle2">Q2 资产盘点</Typography>
                  <Typography variant="body2" color="text.secondary">字段数: {countKeys(q2Assets)}</Typography>
                  <Typography variant="body2">AssetInventory: {countKeys(q2Assets)} 项</Typography>
                  <Divider sx={{ my: 1 }} />
                  <Typography variant="caption" color="text.secondary" display="block">Q2 LLM 溯源</Typography>
                  <Typography variant="body2">Provider: {String(q2LlmTrace.provider_name || q2LlmTrace.provider_plugin_id || "N/A")}</Typography>
                  <Typography variant="body2">Invocations: {Array.isArray(q2LlmTrace.invocations) ? q2LlmTrace.invocations.length : 0}</Typography>
                </Box>
              </Grid>
              <Grid size={{ xs: 12, md: 4 }}>
                <Box sx={{ p: 2, border: "1px solid", borderColor: "divider", borderRadius: 1 }}>
                  <Typography variant="subtitle2">身份内核</Typography>
                  <Typography variant="body2" color="text.secondary">字段数: {countKeys(identityKernel)}</Typography>
                  <Typography variant="body2">{String(identityKernel.identity_role || identityKernel.role_name || "N/A")}</Typography>
                </Box>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Grid>

      <Grid size={{ xs: 12 }}>
        <Box data-testid="q3-trace-accordion">
          <LLMTracePanel trace={trace} />
        </Box>
      </Grid>
    </Grid>
  );
}

export default Q3EvidencePanel;
