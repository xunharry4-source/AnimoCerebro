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
  Typography,
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import { Link as RouterLink } from "react-router-dom";

import {
  fetchNineQuestionEvidence,
  fetchNineQuestionInference,
  fetchNineQuestionModules,
  fetchNineQuestionRaw,
  fetchNineQuestionSummary,
  fetchNineQuestionTracePayload,
  getQuestionDisplayLabel,
  Q2WhoAmIInferenceView,
  LLMTracePayloadView,
} from "../nineQuestionsApi";
import Q2EvidencePanel from "../../../components/Q2EvidencePanel";
import MountedPluginsZone from "../../../components/MountedPluginsZone";
import LLMTracePanel from "../../../components/LLMTracePanel";
import NineQuestionIntroCard from "../../../components/NineQuestionIntroCard";
import Q2DataTabs from "../../../components/Q2DataTabs";
import NineQuestionRerunButton from "../../../components/NineQuestionRerunButton";
import NineQuestionSectionBoundary from "../../../components/NineQuestionSectionBoundary";
import NineQuestionRawPayloadCard from "../../../components/NineQuestionRawPayloadCard";
import NineQuestionWorkflowNavButton from "../../../components/NineQuestionWorkflowNavButton";
import NineQuestionRecoveryActions from "../../../components/NineQuestionRecoveryActions";
import NineQuestionIntegrationStatusCard from "../../../components/NineQuestionIntegrationStatusCard";
import { sanitizeQ2Evidence, sanitizeQ2Inference } from "../detailSafeData";

function resolveErrorGuidance(errMsg: string): { title: string; action: string } {
  if (errMsg.includes("No active session") || errMsg.includes("没有活动 session")) {
    return {
      title: "当前还没有可读取的九问快照",
      action: "请先运行一次完整的九问推演流程，完成后再回到这个监控页刷新。",
    };
  }
  if (errMsg.includes("尚无快照记录")) {
    return {
      title: "Q2 尚未产生推断结果",
      action: "该问题的推断快照为空。请在 Zentex Brain Runtime 中触发一次全量九问推断，完成后再回到此页查看。",
    };
  }
  return {
    title: "加载数据失败",
    action: "请检查网络连接或确认后台服务状态后刷新重试。",
  };
}

function asRecord(value: unknown): Record<string, any> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, any>) : {};
}

function asStringArray(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item)).filter(Boolean);
  if (typeof value === "string" && value.trim()) return [value.trim()];
  return [];
}

function hasMaterialQ1Summary(evidence: Record<string, any>): boolean {
  const q1Summary = asRecord(evidence.q1_summary);
  const primaryDomain = String(q1Summary.primary_domain || "").trim().toLowerCase();
  return Boolean(
    (primaryDomain && primaryDomain !== "unknown" && primaryDomain !== "n/a") ||
      asStringArray(q1Summary.secondary_domains).length > 0 ||
      asStringArray(q1Summary.uncertainties).length > 0 ||
      String(q1Summary.risk_summary || "").trim(),
  );
}

function pickFirstMaterialContext(...sources: unknown[]): Record<string, any> {
  for (const source of sources) {
    const candidate = asRecord(source);
    if (
      Object.keys(asRecord(candidate.workspace_domain_inference)).length > 0 ||
      Object.keys(asRecord(candidate.q1_scene_model)).length > 0 ||
      Object.keys(asRecord(candidate.q1_uncertainty_profile)).length > 0 ||
      Object.keys(asRecord(candidate.identity_kernel_snapshot)).length > 0 ||
      Object.keys(asRecord(candidate.manual_role_overrides)).length > 0
    ) {
      return candidate;
    }
  }
  return {};
}

function buildQ2EvidenceWithRawFallback(
  rawEvidence: unknown,
  rawPayload: unknown,
  q1Fallback?: {
    inference?: unknown;
    raw?: unknown;
  },
): Record<string, any> {
  const evidence = { ...asRecord(rawEvidence) };
  const rawPayloadRecord = asRecord(rawPayload);
  const q1FallbackInference = asRecord(q1Fallback?.inference);
  const q1FallbackRaw = asRecord(q1Fallback?.raw);
  const contextUpdates = pickFirstMaterialContext(
    rawPayloadRecord.context_updates,
    asRecord(rawPayloadRecord.result).context_updates,
    asRecord(rawPayloadRecord.execution_result).context_updates,
    {
      workspace_domain_inference: q1FallbackInference,
      q1_scene_model: asRecord(q1FallbackRaw.context_updates).q1_scene_model,
      q1_uncertainty_profile: asRecord(q1FallbackRaw.context_updates).q1_uncertainty_profile,
      identity_kernel_snapshot: asRecord(q1FallbackRaw.context_updates).identity_kernel_snapshot,
      manual_role_overrides: asRecord(q1FallbackRaw.context_updates).manual_role_overrides,
    },
  );

  if (!hasMaterialQ1Summary(evidence)) {
    const workspaceDomain = asRecord(contextUpdates.workspace_domain_inference);
    const sceneModel = asRecord(contextUpdates.q1_scene_model);
    const uncertaintyProfile = asRecord(contextUpdates.q1_uncertainty_profile);
    const primaryDomain = workspaceDomain.primary_domain || sceneModel.primary_domain || "";
    const secondaryDomains = asStringArray(workspaceDomain.secondary_domains).length
      ? asStringArray(workspaceDomain.secondary_domains)
      : asStringArray(sceneModel.secondary_domains);
    const uncertainties = asStringArray(workspaceDomain.uncertainties).length
      ? asStringArray(workspaceDomain.uncertainties)
      : asStringArray(uncertaintyProfile.risk_sources);
    const riskSummary =
      workspaceDomain.reasoning_summary ||
      uncertaintyProfile.risk_summary ||
      (asStringArray(uncertaintyProfile.risk_sources).length ? asStringArray(uncertaintyProfile.risk_sources).join(", ") : null);

    if (primaryDomain || secondaryDomains.length > 0 || uncertainties.length > 0 || riskSummary) {
      evidence.q1_summary = {
        ...asRecord(evidence.q1_summary),
        primary_domain: primaryDomain,
        secondary_domains: secondaryDomains,
        uncertainties,
        risk_summary: riskSummary,
      };
    }
  }

  if (!asRecord(evidence.identity_kernel).meta_motivation && contextUpdates.identity_kernel_snapshot) {
    evidence.identity_kernel = {
      ...asRecord(evidence.identity_kernel),
      ...asRecord(contextUpdates.identity_kernel_snapshot),
    };
  }

  if (!evidence.manual_intervention && contextUpdates.manual_role_overrides) {
    evidence.manual_intervention = contextUpdates.manual_role_overrides;
  }

  return evidence;
}

export default function Q2Detail() {
  const qId = "q2";
  const [summary, setSummary] = useState<Record<string, any> | null>(null);
  const [rawPayload, setRawPayload] = useState<Record<string, any> | null>(null);
  const [modulesPayload, setModulesPayload] = useState<Record<string, any> | null>(null);
  const [evidencePayload, setEvidencePayload] = useState<Record<string, any> | null>(null);
  const [inferencePayload, setInferencePayload] = useState<Record<string, any> | null>(null);
  const [tracePayload, setTracePayload] = useState<Record<string, any> | null>(null);
  const [q1InferencePayload, setQ1InferencePayload] = useState<Record<string, any> | null>(null);
  const [q1RawPayload, setQ1RawPayload] = useState<Record<string, any> | null>(null);
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
        fetchNineQuestionInference("q1"),
        fetchNineQuestionRaw("q1"),
      ]);

      const nextErrors: Record<string, string> = {};
      const [
        summaryResult,
        evidenceResult,
        inferenceResult,
        traceResult,
        rawResult,
        modulesResult,
        q1InferenceResult,
        q1RawResult,
      ] = results;

      if (summaryResult.status === "fulfilled") setSummary(summaryResult.value);
      else nextErrors.summary = summaryResult.reason?.message || "加载 Q2 summary 失败";

      if (evidenceResult.status === "fulfilled") setEvidencePayload(evidenceResult.value);
      else nextErrors.evidence = evidenceResult.reason?.message || "加载 Q2 evidence 失败";

      if (inferenceResult.status === "fulfilled") setInferencePayload(inferenceResult.value);
      else nextErrors.inference = inferenceResult.reason?.message || "加载 Q2 inference 失败";

      if (traceResult.status === "fulfilled") setTracePayload(traceResult.value);
      else nextErrors.trace = traceResult.reason?.message || "加载 Q2 trace 失败";

      if (rawResult.status === "fulfilled") setRawPayload(rawResult.value);
      else nextErrors.raw = rawResult.reason?.message || "加载 Q2 raw 失败";

      if (modulesResult.status === "fulfilled") setModulesPayload(modulesResult.value);
      else nextErrors.modules = modulesResult.reason?.message || "加载 Q2 modules 失败";

      if (q1InferenceResult.status === "rejected") {
        nextErrors.q1Inference = q1InferenceResult.reason?.message || "加载 Q1 inference 失败";
      }
      else setQ1InferencePayload(q1InferenceResult.value);
      if (q1RawResult.status === "rejected") {
        nextErrors.q1Raw = q1RawResult.reason?.message || "加载 Q1 raw 失败";
      }
      else setQ1RawPayload(q1RawResult.value);

      setSectionErrors(nextErrors);

      const hardFailures = [summaryResult, rawResult, modulesResult].every((result) => result.status === "rejected");
      if (hardFailures) {
        const firstBaseError = [summaryResult, rawResult, modulesResult].find(
          (result) => result.status === "rejected",
        ) as PromiseRejectedResult | undefined;
        throw new Error(firstBaseError?.reason?.message || "Q2 基础分区全部加载失败，当前无法建立页面上下文。");
      }
    } catch (err: any) {
      setError(err?.message || "加载 Q2 详情失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadDetail();
  }, []);

  if (loading) return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 2, p: 3 }}>
      <CircularProgress size={24} />
      <Typography variant="body2" color="text.secondary">正在加载 Q2 身份审计数据...</Typography>
    </Box>
  );

  if (error) {
    const guidance = resolveErrorGuidance(error);
    return (
      <Box sx={{ p: 3 }} data-testid="q2-error-boundary">
        <Alert severity="error" sx={{ mb: 2 }}>
          <AlertTitle>{guidance.title}</AlertTitle>
          <Typography variant="body2"><strong>建议操作：</strong> {guidance.action}</Typography>
        </Alert>
        <Button variant="outlined" startIcon={<RefreshIcon />} onClick={() => void loadDetail()}>重新加载</Button>
      </Box>
    );
  }

  const q1Fallback = {
    inference: q1InferencePayload,
    raw: q1RawPayload,
  };
  const rawEvidence = buildQ2EvidenceWithRawFallback(evidencePayload, rawPayload, q1Fallback);
  const rawInference = inferencePayload;
  const sanitizedEvidence = sanitizeQ2Evidence(rawEvidence);
  const sanitizedInference = sanitizeQ2Inference(rawInference);
  const evidence = sanitizedEvidence.value;
  const inference = sanitizedInference.value as Q2WhoAmIInferenceView | null;
  const llmTrace = tracePayload;
  const hasStructuredSnapshot = Boolean(
    evidencePayload ||
      rawInference ||
      Object.keys(rawEvidence).length > 0,
  );
  const showIncompleteAlert = Boolean(
    sectionErrors.evidence ||
      sectionErrors.inference ||
      !evidencePayload ||
      !rawInference,
  );
  const detailWarnings = [...sanitizedEvidence.warnings, ...sanitizedInference.warnings];
  const mountedPlugins = Array.isArray(rawPayload?.mounted_plugins) ? rawPayload?.mounted_plugins : [];
  const providerName = String(tracePayload?.provider_name || rawPayload?.provider_name || rawPayload?.llm_trace_payload?.provider_name || "");
  const traceId = String(rawPayload?.trace_id || "");
  const toolId = String(rawPayload?.tool_id || `nine_questions.${qId}`);
  const pageStatus = String(summary?.status || modulesPayload?.status?.status || "partial");
  const executionDiagnosis = rawPayload?.context_updates?.q2_execution_diagnosis || null;
  const recoveryPlan = executionDiagnosis?.recovery_plan || null;

  return (
    <Box data-testid="q2-detail-root">
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Box>
          <Typography variant="h4" gutterBottom>{getQuestionDisplayLabel(qId)} 正式审计页</Typography>
          <Typography variant="body2" color="text.secondary">Mission Continuity & Role Identity Audit（独立接口 GET /nine-questions/q2）</Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <NineQuestionRerunButton qId={qId} onCompleted={loadDetail} />
          <NineQuestionWorkflowNavButton qId={qId} />
          <Button component={RouterLink} to="/console/nine-questions/q2/test" variant="contained" color="warning" data-testid="q2-sandbox-nav-button">进入独立沙箱测试</Button>
        </Stack>
      </Stack>

      <NineQuestionIntroCard questionId="q2" />
      {executionDiagnosis ? (
        <Alert severity={executionDiagnosis.authenticity_status === "completed" ? "success" : "warning"} sx={{ mb: 2 }}>
          <AlertTitle>
            {executionDiagnosis.authenticity_status === "completed" ? "Q2 真实性状态：已验证完成" : "Q2 真实性状态：降级/部分失败"}
          </AlertTitle>
          <Typography variant="body2">
            {String(executionDiagnosis.diagnosis_message || "当前没有诊断说明。")}
          </Typography>
          <Typography variant="body2" sx={{ mt: 1 }}>
            {executionDiagnosis.used_fallback ? "本次使用了 fallback，角色推理不是完整真实链。" : "本次未使用 fallback。"}
          </Typography>
        </Alert>
      ) : null}
      {recoveryPlan ? (
        <Alert severity="info" sx={{ mb: 2 }} data-testid="q2-recovery-plan">
          <AlertTitle>Q2 失败恢复计划</AlertTitle>
          <NineQuestionRecoveryActions qId={qId} recoveryPlan={recoveryPlan} onCompleted={loadDetail} />
        </Alert>
      ) : null}
      {showIncompleteAlert ? (
        <Alert severity="info" sx={{ mb: 3 }}>
          Q2 当前只拿到了部分分区数据，页面已按可用结果降级展示。
        </Alert>
      ) : null}
      <Typography variant="h6" sx={{ mb: 1, fontWeight: "bold" }}>
        Q2 数据详情
      </Typography>
      <NineQuestionSectionBoundary title="Q2 数据详情">
        {sectionErrors.summary ? <Alert severity="warning" sx={{ mb: 2 }}>{sectionErrors.summary}</Alert> : null}
        {sectionErrors.evidence ? <Alert severity="warning" sx={{ mb: 2 }}>{sectionErrors.evidence}</Alert> : null}
        {sectionErrors.inference ? <Alert severity="warning" sx={{ mb: 2 }}>{sectionErrors.inference}</Alert> : null}
        <Q2DataTabs
          evidence={hasStructuredSnapshot ? evidence : null}
          inference={inference}
        />
      </NineQuestionSectionBoundary>


      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Stack direction="row" spacing={1} sx={{ mb: 2 }} useFlexGap flexWrap="wrap">
            <Chip label={pageStatus} color="primary" data-testid="q2-cache-status-chip" />
            <Chip label={providerName || "-"} variant="outlined" />
            <Chip label={toolId} variant="outlined" sx={{ fontFamily: "monospace" }} />
            {traceId && <Chip label={`trace: ${traceId}`} variant="outlined" sx={{ fontFamily: "monospace" }} data-testid="q2-trace-chip" />}
            {inference?.role_profile?.active_role && (
              <Chip label={`活跃角色: ${inference.role_profile.active_role}`} color="secondary" data-testid="q2-active-role-chip" />
            )}
          </Stack>

          <MountedPluginsZone plugins={mountedPlugins} />

          <Typography variant="h6" gutterBottom sx={{ mt: 2 }}>Q2 结构化证据</Typography>
          <NineQuestionSectionBoundary title="Q2 结构化证据">
            {sectionErrors.modules ? <Alert severity="warning" sx={{ mb: 2 }}>{sectionErrors.modules}</Alert> : null}
            {hasStructuredSnapshot ? (
              <Q2EvidencePanel
                evidence={evidence}
                inference={inference}
                providerName={providerName || null}
                elapsedMs={tracePayload?.elapsed_ms || rawPayload?.llm_trace_payload?.elapsed_ms || 0}
              />
            ) : <Alert severity="warning">无结构化证据。</Alert>}
          </NineQuestionSectionBoundary>
        </CardContent>
      </Card>

      <NineQuestionIntegrationStatusCard qId={qId} modulesPayload={modulesPayload} />

      {detailWarnings.length > 0 || !rawEvidence || !rawInference ? (
        <NineQuestionRawPayloadCard
          title="Q2 原始字段诊断"
          warnings={detailWarnings}
          payloads={[
            { label: "summary", value: summary },
            { label: "modules", value: modulesPayload },
            { label: "preprocessed_evidence", value: rawEvidence },
            { label: "inference_result", value: rawInference },
            { label: "raw", value: rawPayload },
          ]}
        />
      ) : null}

      <NineQuestionSectionBoundary title="Q2 Trace">
        {sectionErrors.trace ? <Alert severity="warning" sx={{ mb: 2 }}>{sectionErrors.trace}</Alert> : null}
        <LLMTracePanel trace={llmTrace as LLMTracePayloadView} />
      </NineQuestionSectionBoundary>
    </Box>
  );
}
