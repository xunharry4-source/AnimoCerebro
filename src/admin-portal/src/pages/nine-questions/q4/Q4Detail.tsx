import { useEffect, useState } from "react";
import {
  Alert,
  AlertTitle,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableRow,
  Typography,
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import { useTranslation } from "react-i18next";
import { Link as RouterLink } from "react-router-dom";

import {
  fetchNineQuestionEvidence,
  fetchNineQuestionInference,
  fetchNineQuestionModules,
  fetchNineQuestionRaw,
  fetchNineQuestionSummary,
  fetchNineQuestionTracePayload,
  getQuestionDisplayLabel,
  LLMTracePayloadView,
  Q4PreprocessedEvidence,
  Q4WhatCanIDoInferenceView,
} from "../nineQuestionsApi";
import LLMTracePanel from "../../../components/LLMTracePanel";
import NineQuestionIntroCard from "../../../components/NineQuestionIntroCard";
import MountedPluginsZone from "../../../components/MountedPluginsZone";
import Q4EvidencePanel from "../../../components/Q4EvidencePanel";
import Q4DataTabs from "../../../components/Q4DataTabs";
import NineQuestionRerunButton from "../../../components/NineQuestionRerunButton";
import NineQuestionRecoveryActions from "../../../components/NineQuestionRecoveryActions";
import NineQuestionSectionBoundary from "../../../components/NineQuestionSectionBoundary";
import NineQuestionRawPayloadCard from "../../../components/NineQuestionRawPayloadCard";
import NineQuestionWorkflowNavButton from "../../../components/NineQuestionWorkflowNavButton";
import NineQuestionIntegrationStatusCard from "../../../components/NineQuestionIntegrationStatusCard";
import NineQuestionAnswerTable from "../../../components/NineQuestionAnswerTable";
import { sanitizeQ4Evidence, sanitizeQ4Inference } from "../detailSafeData";

function resolveErrorGuidance(errMsg: string, t: (key: string) => string): { title: string; action: string } {
  if (errMsg.includes("No active session") || errMsg.includes("没有活动 session")) {
    return {
      title: t("nineQuestions.q4.noActiveSession"),
      action: t("nineQuestions.q4.actionRunDeduction"),
    };
  }
  if (errMsg.includes("尚无快照记录")) {
    return {
      title: t("nineQuestions.q4.noInferenceResult"),
      action: t("nineQuestions.q4.actionTriggerFullDeduction"),
    };
  }
  if (errMsg.includes("状态机未挂载") || errMsg.includes("503")) {
    return {
      title: t("nineQuestions.q4.engineNotReady"),
      action: t("nineQuestions.q4.checkRuntimeStatus"),
    };
  }
  return {
    title: t("nineQuestions.q4.loadFailed"),
    action: t("nineQuestions.q4.retryHint"),
  };
}

function statusColor(status: string): "success" | "warning" | "error" | "default" {
  const normalized = status.toLowerCase();
  if (["completed", "success", "ok"].includes(normalized)) return "success";
  if (["failed", "error", "missing"].includes(normalized)) return "error";
  if (["degraded", "partial", "partial_failed", "running"].includes(normalized)) return "warning";
  return "default";
}

function asList(value: unknown): Record<string, any>[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, any> => item !== null && typeof item === "object" && !Array.isArray(item));
}

function asRecord(value: unknown): Record<string, any> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, any>) : {};
}

function hasMaterialValue(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(hasMaterialValue);
  if (value && typeof value === "object") {
    return Object.values(value as Record<string, any>).some(hasMaterialValue);
  }
  return value !== undefined && value !== null && value !== "";
}

function firstMaterialRecord(...values: unknown[]): Record<string, any> {
  for (const value of values) {
    const candidate = asRecord(value);
    if (hasMaterialValue(candidate)) return candidate;
  }
  return {};
}

function firstMaterialValue(...values: unknown[]): unknown {
  return values.find(hasMaterialValue);
}

function hasRenderableQ4Evidence(value: unknown): boolean {
  const payload = asRecord(value);
  const q1 = asRecord(payload.q1_context);
  const q2 = asRecord(payload.q2_context);
  const q3 = asRecord(payload.q3_inventory);
  const q1Scene = asRecord(q1.scene_model);
  const q2Inventory = asRecord(q2.asset_inventory);
  const q2Resource = asRecord(q2.resource_evaluation);
  const q3Role = asRecord(q3.role_profile);
  const q3Mission = asRecord(q3.mission_boundary);
  return [
    q1Scene.primary_domain,
    q1Scene.secondary_domains,
    q2Inventory.cognitive_and_functional_tools,
    q2Inventory.execution_domains,
    q2Resource.resource_status,
    q3Role.active_role,
    q3Role.identity_role,
    q3Mission.priority_duties,
    q3Mission.current_mission,
    q3.capability_baseline,
    q3.available_execution_tools,
  ].some(hasMaterialValue);
}

function hasMaterialEvidence(value: unknown): boolean {
  const payload = asRecord(value);
  return Object.values(payload).some((item) => {
    if (Array.isArray(item)) return item.length > 0;
    if (item && typeof item === "object") return Object.keys(item as Record<string, any>).length > 0;
    return item !== undefined && item !== null && item !== "";
  });
}

function buildQ4EvidenceWithRawFallback(rawEvidence: unknown, rawPayload: unknown): Record<string, any> {
  const evidence = { ...asRecord(rawEvidence) };
  if (hasRenderableQ4Evidence(evidence)) return evidence;

  const raw = asRecord(rawPayload);
  const contextUpdates = asRecord(raw.context_updates);
  const rawResult = asRecord(raw.result);
  const resultContextUpdates = asRecord(rawResult.context_updates);
  const traceContext = firstMaterialRecord(
    asRecord(raw.llm_trace_payload).context_data,
    asRecord(contextUpdates.llm_trace_payload).context_data,
    asRecord(rawResult.llm_trace_payload).context_data,
  );
  const preprocessed = asRecord(
    contextUpdates.q4_preprocessed_evidence ||
      rawResult.q4_preprocessed_evidence ||
      resultContextUpdates.q4_preprocessed_evidence,
  );
  if (hasRenderableQ4Evidence(preprocessed)) {
    return preprocessed;
  }

  const capabilityEvidence = asRecord(
    contextUpdates.q4_capability_evidence ||
      rawResult.q4_capability_evidence ||
      resultContextUpdates.q4_capability_evidence,
  );
  const assetAndPermissions = asRecord(preprocessed.asset_and_permissions);
  const capabilityBaseline = firstMaterialRecord(contextUpdates.q4_capability_baseline, rawResult.q4_capability_baseline, traceContext.capability_baseline);
  const q2UnifiedInventory = firstMaterialRecord(
    assetAndPermissions.q2_unified_asset_inventory,
    capabilityEvidence.q2_unified_asset_inventory,
    contextUpdates.q2_unified_asset_inventory,
    traceContext.q2_unified_asset_inventory,
  );
  const q2AssetInventory = firstMaterialRecord(
    assetAndPermissions.q2_external_tool_asset_inventory,
    traceContext.q2_external_tool_asset_inventory,
    capabilityEvidence.q2_external_tool_asset_inventory,
    capabilityEvidence.q2_asset_inventory,
    contextUpdates.q2_external_tool_asset_inventory,
    contextUpdates.q2_asset_inventory,
    contextUpdates.asset_inventory,
  );
  const q2ResourceEvaluation = firstMaterialRecord(
    capabilityEvidence.q2_resource_evaluation,
    contextUpdates.q2_resource_evaluation,
    traceContext.q2_resource_evaluation,
  );
  const q3RoleProfile = firstMaterialRecord(capabilityEvidence.q3_role_profile, contextUpdates.q3_role_profile, traceContext.q3_role_profile);
  const q3MissionBoundary = firstMaterialRecord(capabilityEvidence.q3_mission_boundary, contextUpdates.q3_mission_boundary, traceContext.q3_mission_boundary);
  const q1SceneModel = firstMaterialRecord(capabilityEvidence.q1_scene_model, contextUpdates.q1_scene_model, traceContext.q1_scene_model);
  const q1UncertaintyProfile = firstMaterialRecord(contextUpdates.q1_uncertainty_profile, traceContext.q1_uncertainty_profile);

  return {
    q1_context: {
      scene_model: q1SceneModel,
      uncertainty_profile: q1UncertaintyProfile,
    },
    q2_context: {
      asset_inventory: q2AssetInventory,
      resource_evaluation: q2ResourceEvaluation,
    },
    q3_inventory: {
      available_cognitive_tools: q2UnifiedInventory.available_cognitive_tools || [],
      available_execution_tools: q2UnifiedInventory.available_execution_tools || [],
      connected_agents: Array.isArray(q2UnifiedInventory.connected_agents) ? q2UnifiedInventory.connected_agents : [],
      activated_strategy_patches: q2UnifiedInventory.activated_strategy_patches || [],
      accessible_workspace_zones: q2UnifiedInventory.accessible_workspace_zones || [],
      permission_profile: firstMaterialRecord(contextUpdates.q4_permission_profile, assetAndPermissions.permission_profile, traceContext.permission_profile),
      active_execution_domains: firstMaterialValue(contextUpdates.q4_active_execution_domains, traceContext.active_execution_domains) || [],
      capability_baseline: capabilityBaseline,
      resource_evaluation: q2ResourceEvaluation,
      role_profile: q3RoleProfile,
      mission_boundary: q3MissionBoundary,
    },
  };
}

function buildQ4InferenceWithRawFallback(rawInference: unknown, rawPayload: unknown): Record<string, any> | null {
  const inference = asRecord(rawInference);
  if (hasMaterialEvidence(inference)) return inference;
  const raw = asRecord(rawPayload);
  const contextUpdates = asRecord(raw.context_updates);
  const rawResult = asRecord(raw.result);
  const resultContextUpdates = asRecord(rawResult.context_updates);
  const fallback = asRecord(
    contextUpdates.q4_capability_boundary_profile ||
      rawResult.q4_capability_boundary_profile ||
      rawResult.capability_boundary_profile ||
      resultContextUpdates.q4_capability_boundary_profile,
  );
  return hasMaterialEvidence(fallback) ? fallback : null;
}

function hasMaterialTracePayload(value: unknown): value is Record<string, any> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const payload = value as Record<string, any>;
  if (Array.isArray(payload.invocations) && payload.invocations.some(hasMaterialTracePayload)) return true;
  return ["provider_name", "model", "prompt", "system_prompt", "context_data", "raw_response", "error_type", "error_message"].some((key) => {
    const item = payload[key];
    if (Array.isArray(item)) return item.length > 0;
    if (item && typeof item === "object") return Object.keys(item).length > 0;
    return item !== undefined && item !== null && item !== "";
  });
}

export default function Q4Detail() {
  const { t } = useTranslation();
  const qId = "q4";
  const [summary, setSummary] = useState<Record<string, any> | null>(null);
  const [rawPayload, setRawPayload] = useState<Record<string, any> | null>(null);
  const [modulesPayload, setModulesPayload] = useState<Record<string, any> | null>(null);
  const [evidencePayload, setEvidencePayload] = useState<Record<string, any> | null>(null);
  const [inferencePayload, setInferencePayload] = useState<Record<string, any> | null>(null);
  const [tracePayload, setTracePayload] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sectionErrors, setSectionErrors] = useState<Record<string, string>>({});

  const loadDetail = async () => {
    setLoading(true);
    setError(null);
    setSectionErrors({});
    try {
      const results = await Promise.allSettled([
        fetchNineQuestionSummary(qId),
        fetchNineQuestionEvidence(qId),
        fetchNineQuestionInference(qId),
        fetchNineQuestionTracePayload(qId),
        fetchNineQuestionRaw(qId),
        fetchNineQuestionModules(qId),
      ]);

      const nextErrors: Record<string, string> = {};
      const [summaryResult, evidenceResult, inferenceResult, traceResult, rawResult, modulesResult] = results;

      if (summaryResult.status === "fulfilled") setSummary(summaryResult.value);
      else nextErrors.summary = summaryResult.reason?.message || t("nineQuestions.q4.loadSummaryFailed");

      if (evidenceResult.status === "fulfilled") setEvidencePayload(evidenceResult.value);
      else nextErrors.evidence = evidenceResult.reason?.message || t("nineQuestions.q4.loadEvidenceFailed");

      if (inferenceResult.status === "fulfilled") setInferencePayload(inferenceResult.value);
      else nextErrors.inference = inferenceResult.reason?.message || t("nineQuestions.q4.loadInferenceFailed");

      if (traceResult.status === "fulfilled") setTracePayload(traceResult.value);
      else nextErrors.trace = traceResult.reason?.message || t("nineQuestions.q4.loadTraceFailed");

      if (rawResult.status === "fulfilled") setRawPayload(rawResult.value);
      else nextErrors.raw = rawResult.reason?.message || t("nineQuestions.q4.loadRawFailed");

      if (modulesResult.status === "fulfilled") setModulesPayload(modulesResult.value);
      else nextErrors.modules = modulesResult.reason?.message || t("nineQuestions.q4.loadModulesFailed");

      setSectionErrors(nextErrors);

      const hardFailures = [summaryResult, rawResult, modulesResult].every((result) => result.status === "rejected");
      if (hardFailures) {
        const reasons = [summaryResult, rawResult, modulesResult]
          .map((result) => (result.status === "rejected" ? result.reason?.message : ""))
          .filter(Boolean);
        throw new Error(reasons.join("；") || t("nineQuestions.q4.basePartitionsFailed"));
      }
    } catch (err: any) {
      setError(err?.message || t("nineQuestions.q4.loadDetailFailed"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadDetail();
  }, []);

  if (loading) {
    return (
      <Box sx={{ display: "flex", alignItems: "center", gap: 2, p: 3 }}>
        <CircularProgress size={24} />
        <Typography variant="body2" color="text.secondary">{t("nineQuestions.q4.loading")}</Typography>
      </Box>
    );
  }

  if (error) {
    const guidance = resolveErrorGuidance(error, t);
    return (
      <Box sx={{ p: 3 }} data-testid="q4-error-boundary">
        <Alert severity="error" sx={{ mb: 2 }}>
          <AlertTitle>{guidance.title}</AlertTitle>
          <Typography variant="body2"><strong>{t("nineQuestions.q4.suggestedAction")}：</strong> {guidance.action}</Typography>
          <Typography variant="body2" sx={{ mt: 1 }}>{error}</Typography>
        </Alert>
        <Button variant="outlined" startIcon={<RefreshIcon />} onClick={() => void loadDetail()} data-testid="q4-retry-button">{t("common.refresh")}</Button>
      </Box>
    );
  }

  const rawEvidence = buildQ4EvidenceWithRawFallback(evidencePayload, rawPayload);
  const rawInference = buildQ4InferenceWithRawFallback(inferencePayload, rawPayload);
  const sanitizedEvidence = sanitizeQ4Evidence(rawEvidence);
  const sanitizedInference = sanitizeQ4Inference(rawInference);
  const evidence = sanitizedEvidence.value as Q4PreprocessedEvidence;
  const inference = sanitizedInference.value as Q4WhatCanIDoInferenceView | null;
  const executionDiagnosis = rawPayload?.context_updates?.q4_execution_diagnosis || null;
  const recoveryPlan = executionDiagnosis?.recovery_plan || null;
  const hasStructuredSnapshot = hasMaterialEvidence(rawEvidence);
  const pageStatus = String(summary?.status || modulesPayload?.status?.status || "partial");
  const showIncompleteAlert = !hasStructuredSnapshot || !inference || pageStatus.includes("partial");
  const detailWarnings = [...sanitizedEvidence.warnings, ...sanitizedInference.warnings];
  const materialTracePayload = hasMaterialTracePayload(tracePayload)
    ? tracePayload
    : hasMaterialTracePayload(rawPayload?.llm_trace_payload)
      ? rawPayload?.llm_trace_payload
      : hasMaterialTracePayload(rawPayload?.context_updates?.llm_trace_payload)
        ? rawPayload?.context_updates?.llm_trace_payload
        : null;
  const providerName = String(materialTracePayload?.provider_name || rawPayload?.llm_trace_payload?.provider_name || "");
  const traceId = String(rawPayload?.trace_id || "");
  const toolId = String(rawPayload?.tool_id || `nine_questions.${qId}`);
  const moduleRuns = asList(modulesPayload?.module_runs || executionDiagnosis?.module_runs);
  const pluginRuns = asList(modulesPayload?.plugin_runs || executionDiagnosis?.plugin_runs);
  const upstreamDependencies = asList(modulesPayload?.upstream_dependencies || executionDiagnosis?.upstream_dependencies);

  return (
    <Box data-testid="q4-detail-root" sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0 }}>
        <Box>
          <Typography variant="h4" fontWeight="bold" gutterBottom>{getQuestionDisplayLabel(qId)} {t("nineQuestions.q4.productionAudit")}</Typography>
          <Typography variant="body2" color="text.secondary">{t("nineQuestions.q4.subtitle")}</Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <NineQuestionRerunButton qId={qId} onCompleted={loadDetail} />
          <NineQuestionWorkflowNavButton qId={qId} />
          <Button component={RouterLink} to="/console/nine-questions/q4/test" variant="contained" color="warning">{t("nineQuestions.q4.enterSandbox")}</Button>
        </Stack>
      </Stack>

      <NineQuestionIntroCard questionId="q4" />
      {executionDiagnosis ? (
        <Alert severity={executionDiagnosis.authenticity_status === "completed" ? "success" : "warning"}>
          <AlertTitle>
            {executionDiagnosis.authenticity_status === "completed" ? t("nineQuestions.q4.authCompleted") : t("nineQuestions.q4.authPartial")}
          </AlertTitle>
          <Typography variant="body2">{String(executionDiagnosis.diagnosis_message || t("nineQuestions.q4.noDiagnosis"))}</Typography>
          <Typography variant="body2" sx={{ mt: 1 }}>
            {executionDiagnosis.used_fallback ? t("nineQuestions.q4.fallbackUsed") : t("nineQuestions.q4.noFallbackUsed")}
          </Typography>
        </Alert>
      ) : null}
      {recoveryPlan ? (
        <Alert severity="info" data-testid="q4-recovery-plan">
          <AlertTitle>{t("nineQuestions.q4.recoveryPlan")}</AlertTitle>
          <NineQuestionRecoveryActions qId={qId} recoveryPlan={recoveryPlan} onCompleted={loadDetail} />
        </Alert>
      ) : null}
      {showIncompleteAlert ? (
        <Alert severity="info">
          {t("nineQuestions.q4.partialData")}
        </Alert>
      ) : null}
      <NineQuestionAnswerTable questionId={qId} inference={inference} result={rawPayload?.result} />

      <NineQuestionSectionBoundary title={t("nineQuestions.q4.dataDetails")}>
        {sectionErrors.summary ? <Alert severity="warning" sx={{ mb: 2 }}>{sectionErrors.summary}</Alert> : null}
        {sectionErrors.evidence ? <Alert severity="warning" sx={{ mb: 2 }}>{sectionErrors.evidence}</Alert> : null}
        {sectionErrors.inference ? <Alert severity="warning" sx={{ mb: 2 }}>{sectionErrors.inference}</Alert> : null}
        <Q4DataTabs evidence={hasStructuredSnapshot ? evidence : null} inference={inference} />
      </NineQuestionSectionBoundary>

      <Card variant="outlined" data-testid="q4-module-audit">
        <CardContent>
          <Stack direction="row" spacing={1} sx={{ mb: 2 }} useFlexGap flexWrap="wrap">
            <Chip label={pageStatus} color={statusColor(pageStatus)} data-testid="q4-cache-status-chip" />
            {providerName ? <Chip label={providerName} variant="outlined" /> : null}
            <Chip label={toolId} variant="outlined" sx={{ fontFamily: "monospace" }} />
            {traceId ? <Chip label={`trace: ${traceId}`} variant="outlined" sx={{ fontFamily: "monospace" }} data-testid="q4-trace-chip" /> : null}
          </Stack>
          <Typography variant="body2" sx={{ mb: 2 }}>
            {t("nineQuestions.q4.moduleSummary", { modules: moduleRuns.length, plugins: pluginRuns.length, dependencies: upstreamDependencies.length })}
          </Typography>
          <TableContainer>
            <Table size="small">
              <TableBody>
                {[...moduleRuns, ...pluginRuns, ...upstreamDependencies].map((run, index) => {
                  const id = String(run.module_id || run.plugin_id || run.dependency_id || `run-${index}`);
                  const status = String(run.status || "unknown");
                  return (
                    <TableRow key={`${id}-${index}`} hover>
                      <TableCell sx={{ width: "35%", fontFamily: "monospace" }}>{id}</TableCell>
                      <TableCell sx={{ width: "20%" }}>
                        <Chip size="small" label={status} color={statusColor(status)} />
                      </TableCell>
                      <TableCell sx={{ width: "20%", fontFamily: "monospace" }}>{String(run.error_code || run.feature_code || "")}</TableCell>
                      <TableCell>{String(run.error_message || run.message || "")}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
          <MountedPluginsZone plugins={rawPayload?.mounted_plugins || []} />
        </CardContent>
      </Card>

      {!hasStructuredSnapshot ? (
        <Alert severity="warning">
          {t("nineQuestions.q4.noStructuredEvidenceLayout")}
        </Alert>
      ) : null}

      <NineQuestionSectionBoundary title={t("nineQuestions.q4.structuredEvidenceSection")}>
        {sectionErrors.modules ? <Alert severity="warning" sx={{ mb: 2 }}>{sectionErrors.modules}</Alert> : null}
        <Card variant="outlined">
          <CardContent>
            <Typography variant="h6" gutterBottom sx={{ mt: 0, fontWeight: "bold" }}>
              {t("nineQuestions.q4.structuredCapabilityEvidence")}
            </Typography>
            {hasStructuredSnapshot ? (
              <Q4EvidencePanel
                evidence={evidence}
                inference={inference}
                providerName={providerName || null}
                elapsedMs={Number(materialTracePayload?.elapsed_ms || rawPayload?.llm_trace_payload?.elapsed_ms || 0)}
              />
            ) : (
              <Alert severity="warning">{t("nineQuestions.q4.noStructuredCapabilityEvidence")}</Alert>
            )}
          </CardContent>
        </Card>
      </NineQuestionSectionBoundary>

      <NineQuestionIntegrationStatusCard qId={qId} modulesPayload={modulesPayload} />

      {detailWarnings.length > 0 || !evidencePayload || !inferencePayload ? (
        <NineQuestionRawPayloadCard
          title={t("nineQuestions.q4.rawDiagnostics")}
          warnings={detailWarnings}
          payloads={[
            { label: "summary", value: summary },
            { label: "modules", value: modulesPayload },
            { label: "preprocessed_evidence", value: evidencePayload },
            { label: "inference_result", value: inferencePayload },
            { label: "raw", value: rawPayload },
          ]}
        />
      ) : null}

      <NineQuestionSectionBoundary title={t("nineQuestions.q4.traceSection")}>
        {sectionErrors.trace ? <Alert severity="warning" sx={{ mb: 2 }}>{sectionErrors.trace}</Alert> : null}
        <LLMTracePanel trace={materialTracePayload as LLMTracePayloadView | null} />
      </NineQuestionSectionBoundary>
    </Box>
  );
}
