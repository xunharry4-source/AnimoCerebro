import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
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
  WorkspaceDomainInferenceView,
  LLMTracePayloadView,
} from "../nineQuestionsApi";
import Q1EvidencePanel from "../../../components/Q1EvidencePanel";
import LLMTracePanel from "../../../components/LLMTracePanel";
import MountedPluginsZone from "../../../components/MountedPluginsZone";
import Q1UpgradePanel from "../../../components/Q1UpgradePanel";
import NineQuestionIntroCard from "../../../components/NineQuestionIntroCard";
import Q1DataTabs from "../../../components/Q1DataTabs";
import NineQuestionRerunButton from "../../../components/NineQuestionRerunButton";
import NineQuestionSectionBoundary from "../../../components/NineQuestionSectionBoundary";
import NineQuestionRawPayloadCard from "../../../components/NineQuestionRawPayloadCard";
import NineQuestionWorkflowNavButton from "../../../components/NineQuestionWorkflowNavButton";
import NineQuestionIntegrationStatusCard from "../../../components/NineQuestionIntegrationStatusCard";
import NineQuestionAnswerTable from "../../../components/NineQuestionAnswerTable";
import { sanitizeQ1Evidence, sanitizeQ1Inference } from "../detailSafeData";

// Maps HTTP error context → human-readable guidance
function resolveErrorGuidance(errMsg: string, t: (key: string) => string): { title: string; action: string } {
  if (errMsg.includes("No active session") || errMsg.includes("没有活动 session")) {
    return {
      title: "当前还没有可读取的九问快照",
      action: "请先运行一次完整的九问推演流程，完成后再回到这个监控页刷新。",
    };
  }
  if (errMsg.includes("尚无快照记录")) {
    return {
      title: t("nineQuestions.q1.noInferenceResult"),
      action: t("nineQuestions.q1.actionTriggerFullDeduction"),
    };
  }
  if (errMsg.includes("状态机未挂载") || errMsg.includes("503")) {
    return {
      title: t("nineQuestions.q1.engineNotReady"),
      action: t("nineQuestions.q1.checkRuntimeStatus"),
    };
  }
  if (errMsg.includes("NetworkError") || errMsg.includes("Failed to fetch")) {
    return {
      title: t("nineQuestions.q1.networkFailed"),
      action: t("nineQuestions.q1.checkNetworkOrDevServer"),
    };
  }
  return {
    title: t("nineQuestions.q1.loadFailed"),
    action: t("nineQuestions.q1.retryHint"),
  };
}

function resolveQ1StatusGuidance(
  status: string,
  errorMessage: string,
): { severity: "info" | "warning" | "error"; title: string; body: string } | null {
  if (status === "partial_failed") {
    return {
      severity: "warning",
      title: "Q1 本次推演部分失败",
      body: errorMessage || "部分分区可用，但推断链路未完整成功；当前页面只展示仍可确认的证据。",
    };
  }
  if (status === "failed") {
    return {
      severity: "error",
      title: "Q1 本次推演失败",
      body: errorMessage || "当前没有可用的推断结果；请检查失败原因后重新执行 Q1。",
    };
  }
  if (status === "stale") {
    return {
      severity: "warning",
      title: "Q1 结果未提交完成",
      body: errorMessage || "检测到未完成写入，系统已隐藏半写结果；请重新执行 Q1 获取完整快照。",
    };
  }
  return null;
}

function humanizeModuleId(moduleId: string): string {
  return moduleId.replaceAll("_", " ");
}

export default function Q1Detail() {
  const { t } = useTranslation();
  const qId = "q1";
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
      else nextErrors.summary = summaryResult.reason?.message || "加载 Q1 summary 失败";

      if (evidenceResult.status === "fulfilled") setEvidencePayload(evidenceResult.value);
      else nextErrors.evidence = evidenceResult.reason?.message || "加载 Q1 evidence 失败";

      if (inferenceResult.status === "fulfilled") setInferencePayload(inferenceResult.value);
      else nextErrors.inference = inferenceResult.reason?.message || "加载 Q1 inference 失败";

      if (traceResult.status === "fulfilled") setTracePayload(traceResult.value);
      else nextErrors.trace = traceResult.reason?.message || "加载 Q1 trace 失败";

      if (rawResult.status === "fulfilled") setRawPayload(rawResult.value);
      else nextErrors.raw = rawResult.reason?.message || "加载 Q1 raw 失败";

      if (modulesResult.status === "fulfilled") setModulesPayload(modulesResult.value);
      else nextErrors.modules = modulesResult.reason?.message || "加载 Q1 modules 失败";

      setSectionErrors(nextErrors);

      const hardFailures = [summaryResult, rawResult, modulesResult].every((result) => result.status === "rejected");
      if (hardFailures) {
        throw new Error("Q1 基础分区全部加载失败，当前无法建立页面上下文。");
      }
    } catch (err: any) {
      setError(err?.message ?? "加载 Q1 详情失败，原因未知。");
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
        <Typography variant="body2" color="text.secondary">
          {t("nineQuestions.q1.loadingSnapshot")}
        </Typography>
      </Box>
    );
  }

  // ——— 人话降级熔断区 ———
  if (error) {
    const guidance = resolveErrorGuidance(error, t);
    return (
      <Box sx={{ p: 3 }} data-testid="q1-error-boundary">
        <Alert severity="error" sx={{ mb: 2 }}>
          <AlertTitle>{guidance.title}</AlertTitle>
          <Typography variant="body2" sx={{ mt: 0.5 }}>
            <strong>{t("common.nextStep")}: </strong> {guidance.action}
          </Typography>
        </Alert>
        <Button
          variant="outlined"
          startIcon={<RefreshIcon />}
          onClick={() => void loadDetail()}
          data-testid="q1-retry-button"
        >
          {t("nineQuestions.q1.retry")}
        </Button>
      </Box>
    );
  }

  const rawEvidence = evidencePayload;
  const rawInference = inferencePayload;
  const sanitizedEvidence = sanitizeQ1Evidence(rawEvidence);
  const sanitizedInference = sanitizeQ1Inference(rawInference);
  const evidence = sanitizedEvidence.value;
  const inference = sanitizedInference.value;
  const llmTracePayload = tracePayload;
  const q1Upgrade = rawPayload?.q1_llm_upgrade;
  const hasStructuredSnapshot = Boolean(rawEvidence || rawInference);
  const detailWarnings = [...sanitizedEvidence.warnings, ...sanitizedInference.warnings];
  const mountedPlugins = Array.isArray(rawPayload?.mounted_plugins) ? rawPayload?.mounted_plugins : [];
  const providerName = String(tracePayload?.provider_name || rawPayload?.provider_name || rawPayload?.llm_trace_payload?.provider_name || "");
  const traceId = String(rawPayload?.trace_id || "");
  const toolId = String(rawPayload?.tool_id || `nine_questions.${qId}`);
  const pageStatus = String(summary?.status || modulesPayload?.status?.status || "partial");
  const pageErrorMessage = String(modulesPayload?.status?.error_message || "");
  const statusGuidance = resolveQ1StatusGuidance(pageStatus, pageErrorMessage);
  const sourceSummary = modulesPayload?.status?.source_summary as Record<string, any> | undefined;
  const executionDiagnosis = (rawPayload?.context_updates?.q1_execution_diagnosis ||
    modulesPayload?.status?.diagnosis ||
    {}) as Record<string, any>;
  const moduleEntries = Object.entries(modulesPayload?.modules || {}) as Array<[string, Record<string, any>]>;
  const failedModuleEntries = moduleEntries.filter(([, payload]) => String(payload?.status || "") === "failed");

  return (
    <Box data-testid="q1-detail-root">
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 3 }}>
        <Box>
          <Typography variant="h4" gutterBottom>
            {getQuestionDisplayLabel(qId)} {t("nineQuestions.q1.productionAudit")}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Production Snapshot: Workspace &amp; Environment Audit（只读，数据来源 GET /nine-questions/q1）
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <NineQuestionRerunButton qId={qId} onCompleted={loadDetail} />
          <NineQuestionWorkflowNavButton qId={qId} />
          <Button
            component={RouterLink}
            to={`/console/nine-questions/${qId}/test`}
            variant="contained"
            color="warning"
            data-testid="q1-sandbox-nav-button"
          >
            {t("nineQuestions.q1.enterSandbox")}
          </Button>
        </Stack>
      </Stack>

      <NineQuestionIntroCard questionId={qId} />
      {statusGuidance ? (
        <Alert severity={statusGuidance.severity} sx={{ mb: 3 }} data-testid="q1-status-guidance">
          <AlertTitle>{statusGuidance.title}</AlertTitle>
          {statusGuidance.body}
        </Alert>
      ) : null}
      {sourceSummary ? (
        <Alert severity="info" sx={{ mb: 3 }} data-testid="q1-source-guidance">
          <AlertTitle>Q1 结果来源说明</AlertTitle>
          <Box>{String(sourceSummary.display_origin_explanation || "")}</Box>
          <Box sx={{ mt: 1 }}>
            runtime: {String(sourceSummary.physical_and_environment || "unknown")}
          </Box>
          <Box>workspace: {String(sourceSummary.workspace_root || "unknown")}</Box>
          <Box>access_policy: {String(sourceSummary.workspace_access_policy || "unknown")}</Box>
          <Box>structure: {String(sourceSummary.workspace_structure || "unknown")}</Box>
          <Box>structure_source: {String(sourceSummary.structure_source || "unknown")}</Box>
          <Box>sampling: {String(sourceSummary.workspace_content_sampling || "unknown")}</Box>
          <Box>sampling_source: {String(sourceSummary.samples_source || "unknown")}</Box>
          <Box>inference: {String(sourceSummary.domain_inference || "unknown")}</Box>
        </Alert>
      ) : null}
      {!hasStructuredSnapshot ? (
        <Alert severity="info" sx={{ mb: 3 }}>
          Q1 当前只拿到了部分分区数据，页面已按可用结果降级展示。
        </Alert>
      ) : null}
      <NineQuestionAnswerTable questionId={qId} inference={inference} result={rawPayload?.result} />
      <Typography variant="h6" sx={{ mb: 1, fontWeight: "bold" }}>
        Q1 数据详情
      </Typography>
      <NineQuestionSectionBoundary title="Q1 数据详情">
        {sectionErrors.summary ? <Alert severity="warning" sx={{ mb: 2 }}>{sectionErrors.summary}</Alert> : null}
        {sectionErrors.evidence ? <Alert severity="warning" sx={{ mb: 2 }}>{sectionErrors.evidence}</Alert> : null}
        {sectionErrors.inference ? <Alert severity="warning" sx={{ mb: 2 }}>{sectionErrors.inference}</Alert> : null}
        <Q1DataTabs
          evidence={hasStructuredSnapshot ? evidence : null}
          inference={inference}
        />
      </NineQuestionSectionBoundary>


      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          {/* 状态芯片阵列 — 主领域 / 次领域 / 插件 */}
          <Stack direction="row" spacing={1} sx={{ mb: 2 }} useFlexGap flexWrap="wrap">
            <Chip
              label={pageStatus || t("nineQuestions.evidencePanels.unknown")}
              color="primary"
              data-testid="q1-cache-status-chip"
            />
            <Chip label={providerName || "-"} variant="outlined" />
            <Chip
              label={toolId}
              variant="outlined"
              sx={{ fontFamily: "monospace" }}
            />
            {traceId && (
              <Chip
                label={`trace: ${traceId}`}
                variant="outlined"
                sx={{ fontFamily: "monospace" }}
                data-testid="q1-trace-chip"
              />
            )}
            {/* 推断主领域 Chip */}
            {(inference as WorkspaceDomainInferenceView)?.primary_domain && (
              <Chip
                label={`${t("nineQuestions.evidencePanels.primaryDomain")}: ${(inference as WorkspaceDomainInferenceView).primary_domain}`}
                color="secondary"
                data-testid="q1-primary-domain-chip"
              />
            )}
            {/* 次领域 Chips */}
            {(inference as WorkspaceDomainInferenceView)?.secondary_domains?.map(
              (d, idx) => (
                <Chip
                  key={idx}
                  label={d}
                  variant="outlined"
                  size="small"
                  data-testid="q1-secondary-domain-chip"
                />
              ),
            )}
          </Stack>

          {/* 挂载插件清单 */}
          <MountedPluginsZone plugins={mountedPlugins} />

          {failedModuleEntries.length > 0 ? (
            <Alert severity="warning" sx={{ mb: 2 }} data-testid="q1-failed-modules-alert">
              <AlertTitle>Q1 模块级失败</AlertTitle>
              {failedModuleEntries.map(([moduleId, payload]) => (
                <Box key={moduleId}>
                  {humanizeModuleId(moduleId)}: {String(payload?.error || "模块执行失败")}
                </Box>
              ))}
            </Alert>
          ) : null}

          <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: "bold", mt: 2 }}>
            Q1 结构化证据
          </Typography>

          {/* 主证据面板 - Q1EvidencePanel 内部的 Accordion 均默认折叠 */}
          <NineQuestionSectionBoundary title="Q1 结构化证据">
            {sectionErrors.modules ? <Alert severity="warning" sx={{ mb: 2 }}>{sectionErrors.modules}</Alert> : null}
            {hasStructuredSnapshot ? (
              <Q1EvidencePanel
                evidence={evidence}
                inference={inference as WorkspaceDomainInferenceView}
                providerName={providerName || null}
                elapsedMs={tracePayload?.elapsed_ms || rawPayload?.llm_trace_payload?.elapsed_ms || 0}
              />
            ) : (
              <Alert severity="warning">
                {t("nineQuestions.q1.noStructuredEvidence")}
              </Alert>
            )}
          </NineQuestionSectionBoundary>
        </CardContent>
      </Card>

      <Box sx={{ mb: 3 }}>
        <Q1UpgradePanel upgrade={q1Upgrade} />
      </Box>
      <NineQuestionIntegrationStatusCard qId={qId} modulesPayload={modulesPayload} />
      {detailWarnings.length > 0 || !rawEvidence || !rawInference ? (
        <NineQuestionRawPayloadCard
          title="Q1 原始字段诊断"
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

      {/* LLM 交互溯源区 - LLMTracePanel 内部自带 Accordion 默认折叠 */}
      <NineQuestionSectionBoundary title="Q1 Trace">
        {sectionErrors.trace ? <Alert severity="warning" sx={{ mb: 2 }}>{sectionErrors.trace}</Alert> : null}
        <LLMTracePanel trace={llmTracePayload as LLMTracePayloadView} />
      </NineQuestionSectionBoundary>
    </Box>
  );
}
