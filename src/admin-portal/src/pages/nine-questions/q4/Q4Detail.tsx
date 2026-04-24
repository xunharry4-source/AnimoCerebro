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
import { sanitizeQ4Evidence, sanitizeQ4Inference } from "../detailSafeData";

function resolveErrorGuidance(errMsg: string): { title: string; action: string } {
  if (errMsg.includes("No active session") || errMsg.includes("没有活动 session")) {
    return {
      title: "当前还没有可读取的九问快照",
      action: "请先运行一次完整的九问推演流程，完成后再回到这个监控页刷新。",
    };
  }
  if (errMsg.includes("尚无快照记录")) {
    return {
      title: "Q4 尚未产生能力边界快照",
      action: "能力边界审计可能由于 Q1-Q3 前置链路失败或尚未触发。请先重新触发完整九问流程。",
    };
  }
  if (errMsg.includes("状态机未挂载") || errMsg.includes("503")) {
    return {
      title: "后端推演引擎未就绪",
      action: "NineQuestionState 未挂载。请确认 Zentex Brain Runtime 已完成初始化后再刷新。",
    };
  }
  return {
    title: "加载 Q4 数据失败",
    action: "请检查网络、后台服务和 Q4 分区接口状态后刷新重试。",
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

export default function Q4Detail() {
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
      else nextErrors.summary = summaryResult.reason?.message || "加载 Q4 summary 失败";

      if (evidenceResult.status === "fulfilled") setEvidencePayload(evidenceResult.value);
      else nextErrors.evidence = evidenceResult.reason?.message || "加载 Q4 evidence 失败";

      if (inferenceResult.status === "fulfilled") setInferencePayload(inferenceResult.value);
      else nextErrors.inference = inferenceResult.reason?.message || "加载 Q4 inference 失败";

      if (traceResult.status === "fulfilled") setTracePayload(traceResult.value);
      else nextErrors.trace = traceResult.reason?.message || "加载 Q4 trace 失败";

      if (rawResult.status === "fulfilled") setRawPayload(rawResult.value);
      else nextErrors.raw = rawResult.reason?.message || "加载 Q4 raw 失败";

      if (modulesResult.status === "fulfilled") setModulesPayload(modulesResult.value);
      else nextErrors.modules = modulesResult.reason?.message || "加载 Q4 modules 失败";

      setSectionErrors(nextErrors);

      const hardFailures = [summaryResult, rawResult, modulesResult].every((result) => result.status === "rejected");
      if (hardFailures) {
        const reasons = [summaryResult, rawResult, modulesResult]
          .map((result) => (result.status === "rejected" ? result.reason?.message : ""))
          .filter(Boolean);
        throw new Error(reasons.join("；") || "Q4 基础分区全部加载失败，当前无法建立页面上下文。");
      }
    } catch (err: any) {
      setError(err?.message || "加载 Q4 详情失败");
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
        <Typography variant="body2" color="text.secondary">正在加载 Q4 能力边界审计数据...</Typography>
      </Box>
    );
  }

  if (error) {
    const guidance = resolveErrorGuidance(error);
    return (
      <Box sx={{ p: 3 }} data-testid="q4-error-boundary">
        <Alert severity="error" sx={{ mb: 2 }}>
          <AlertTitle>{guidance.title}</AlertTitle>
          <Typography variant="body2"><strong>建议操作：</strong> {guidance.action}</Typography>
          <Typography variant="body2" sx={{ mt: 1 }}>{error}</Typography>
        </Alert>
        <Button variant="outlined" startIcon={<RefreshIcon />} onClick={() => void loadDetail()} data-testid="q4-retry-button">重新加载</Button>
      </Box>
    );
  }

  const sanitizedEvidence = sanitizeQ4Evidence(evidencePayload);
  const sanitizedInference = sanitizeQ4Inference(inferencePayload);
  const evidence = sanitizedEvidence.value as Q4PreprocessedEvidence;
  const inference = sanitizedInference.value as Q4WhatCanIDoInferenceView | null;
  const executionDiagnosis = rawPayload?.context_updates?.q4_execution_diagnosis || null;
  const recoveryPlan = executionDiagnosis?.recovery_plan || null;
  const hasStructuredSnapshot = Boolean(evidencePayload);
  const pageStatus = String(summary?.status || modulesPayload?.status?.status || "partial");
  const showIncompleteAlert = !evidencePayload || !inferencePayload || pageStatus.includes("partial");
  const detailWarnings = [...sanitizedEvidence.warnings, ...sanitizedInference.warnings];
  const providerName = String(tracePayload?.provider_name || rawPayload?.llm_trace_payload?.provider_name || "");
  const traceId = String(rawPayload?.trace_id || "");
  const toolId = String(rawPayload?.tool_id || `nine_questions.${qId}`);
  const moduleRuns = asList(modulesPayload?.module_runs || executionDiagnosis?.module_runs);
  const pluginRuns = asList(modulesPayload?.plugin_runs || executionDiagnosis?.plugin_runs);
  const upstreamDependencies = asList(modulesPayload?.upstream_dependencies || executionDiagnosis?.upstream_dependencies);

  return (
    <Box data-testid="q4-detail-root" sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0 }}>
        <Box>
          <Typography variant="h4" fontWeight="bold" gutterBottom>{getQuestionDisplayLabel(qId)} 正式审计页</Typography>
          <Typography variant="body2" color="text.secondary">Capability Boundary & Actionable Space Audit (Independent API GET /nine-questions/q4)</Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <NineQuestionRerunButton qId={qId} onCompleted={loadDetail} />
          <NineQuestionWorkflowNavButton qId={qId} />
          <Button component={RouterLink} to="/console/nine-questions/q4/test" variant="contained" color="warning">进入独立沙箱测试</Button>
        </Stack>
      </Stack>

      <NineQuestionIntroCard questionId="q4" />
      {executionDiagnosis ? (
        <Alert severity={executionDiagnosis.authenticity_status === "completed" ? "success" : "warning"}>
          <AlertTitle>
            {executionDiagnosis.authenticity_status === "completed" ? "Q4 真实性状态：已验证完成" : "Q4 真实性状态：降级/部分失败"}
          </AlertTitle>
          <Typography variant="body2">{String(executionDiagnosis.diagnosis_message || "当前没有诊断说明。")}</Typography>
          <Typography variant="body2" sx={{ mt: 1 }}>
            {executionDiagnosis.used_fallback ? "本次使用了 fallback，不能视为完整能力边界落地。" : "本次未使用 fallback。"}
          </Typography>
        </Alert>
      ) : null}
      {recoveryPlan ? (
        <Alert severity="info" data-testid="q4-recovery-plan">
          <AlertTitle>Q4 失败恢复计划</AlertTitle>
          <NineQuestionRecoveryActions qId={qId} recoveryPlan={recoveryPlan} onCompleted={loadDetail} />
        </Alert>
      ) : null}
      {showIncompleteAlert ? (
        <Alert severity="info">
          Q4 当前只拿到了部分分区数据，页面已按可用结果降级展示。
        </Alert>
      ) : null}

      <NineQuestionSectionBoundary title="Q4 数据详情">
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
            模块数：{moduleRuns.length} | 插件数：{pluginRuns.length} | 依赖数：{upstreamDependencies.length}
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
          当前没有可用的结构化证据，以下区域保留布局并显示可恢复的空态。
        </Alert>
      ) : null}

      <NineQuestionSectionBoundary title="Q4 结构化证据">
        {sectionErrors.modules ? <Alert severity="warning" sx={{ mb: 2 }}>{sectionErrors.modules}</Alert> : null}
        <Card variant="outlined">
          <CardContent>
            <Typography variant="h6" gutterBottom sx={{ mt: 0, fontWeight: "bold" }}>
              结构化能力边界证据 (Zentex G31A.Q4)
            </Typography>
            {hasStructuredSnapshot ? (
              <Q4EvidencePanel
                evidence={evidence}
                inference={inference}
                providerName={providerName || null}
                elapsedMs={Number(tracePayload?.elapsed_ms || rawPayload?.llm_trace_payload?.elapsed_ms || 0)}
              />
            ) : (
              <Alert severity="warning">暂无结构化能力证据。</Alert>
            )}
          </CardContent>
        </Card>
      </NineQuestionSectionBoundary>

      <NineQuestionIntegrationStatusCard qId={qId} modulesPayload={modulesPayload} />

      {detailWarnings.length > 0 || !evidencePayload || !inferencePayload ? (
        <NineQuestionRawPayloadCard
          title="Q4 原始字段诊断"
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

      <NineQuestionSectionBoundary title="Q4 Trace">
        {sectionErrors.trace ? <Alert severity="warning" sx={{ mb: 2 }}>{sectionErrors.trace}</Alert> : null}
        <LLMTracePanel trace={tracePayload as LLMTracePayloadView} />
      </NineQuestionSectionBoundary>
    </Box>
  );
}
