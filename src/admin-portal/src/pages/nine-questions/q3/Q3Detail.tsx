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
  Q3PreprocessedEvidence,
  Q3WhatDoIHaveInferenceView,
  LLMTracePayloadView,
} from "../nineQuestionsApi";
import Q3EvidencePanel from "../../../components/Q3EvidencePanel";
import MountedPluginsZone from "../../../components/MountedPluginsZone";
import NineQuestionIntroCard from "../../../components/NineQuestionIntroCard";
import Q3DataTabs from "../../../components/Q3DataTabs";
import LLMTracePanel from "../../../components/LLMTracePanel";
import NineQuestionRerunButton from "../../../components/NineQuestionRerunButton";
import NineQuestionSectionBoundary from "../../../components/NineQuestionSectionBoundary";
import NineQuestionRawPayloadCard from "../../../components/NineQuestionRawPayloadCard";
import NineQuestionWorkflowNavButton from "../../../components/NineQuestionWorkflowNavButton";
import NineQuestionRecoveryActions from "../../../components/NineQuestionRecoveryActions";
import NineQuestionIntegrationStatusCard from "../../../components/NineQuestionIntegrationStatusCard";
import NineQuestionAnswerTable from "../../../components/NineQuestionAnswerTable";
import { sanitizeQ3Evidence, sanitizeQ3Inference } from "../detailSafeData";

function resolveErrorGuidance(errMsg: string): { title: string; action: string } {
  if (errMsg.includes("No active session") || errMsg.includes("没有活动 session")) {
    return {
      title: "当前还没有可读取的九问快照",
      action: "请先运行一次完整的九问推演流程，完成后再回到这个监控页刷新。",
    };
  }
  if (errMsg.includes("尚无快照记录")) {
    return {
      title: "Q3 尚未产生推断结果",
      action: "该问题的推断快照为空。资源与工具审计可能由于前置 Q1/Q2 失败而跳过。请在 Zentex Brain Runtime 中重新触发推演。",
    };
  }
  if (errMsg.includes("状态机未挂载") || errMsg.includes("503")) {
    return {
      title: "后端推演引擎未就绪",
      action:
        "NineQuestionState 未挂载到运行时。请检查 Zentex Brain Runtime 的启动状态，确认服务已正确初始化后再刷新。",
    };
  }
  return {
    title: "加载数据失败",
    action: "请检查网络或确认后台服务状态后刷新重试。",
  };
}

export default function Q3Detail() {
  const qId = "q3";
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
      else nextErrors.summary = summaryResult.reason?.message || "加载 Q3 summary 失败";

      if (evidenceResult.status === "fulfilled") setEvidencePayload(evidenceResult.value);
      else nextErrors.evidence = evidenceResult.reason?.message || "加载 Q3 evidence 失败";

      if (inferenceResult.status === "fulfilled") setInferencePayload(inferenceResult.value);
      else nextErrors.inference = inferenceResult.reason?.message || "加载 Q3 inference 失败";

      if (traceResult.status === "fulfilled") setTracePayload(traceResult.value);
      else nextErrors.trace = traceResult.reason?.message || "加载 Q3 trace 失败";

      if (rawResult.status === "fulfilled") setRawPayload(rawResult.value);
      else nextErrors.raw = rawResult.reason?.message || "加载 Q3 raw 失败";

      if (modulesResult.status === "fulfilled") setModulesPayload(modulesResult.value);
      else nextErrors.modules = modulesResult.reason?.message || "加载 Q3 modules 失败";

      setSectionErrors(nextErrors);

      const hardFailures = [summaryResult, rawResult, modulesResult].every((result) => result.status === "rejected");
      if (hardFailures) {
        throw new Error("Q3 基础分区全部加载失败，当前无法建立页面上下文。");
      }
    } catch (err: any) {
      setError(err?.message || "加载 Q3 详情失败");
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
      <Typography variant="body2" color="text.secondary">正在加载 Q3 角色推断数据...</Typography>
    </Box>
  );

  if (error) {
    const guidance = resolveErrorGuidance(error);
    return (
      <Box sx={{ p: 3 }} data-testid="q3-error-boundary">
        <Alert severity="error" sx={{ mb: 2 }}>
          <AlertTitle>{guidance.title}</AlertTitle>
          <Typography variant="body2"><strong>建议操作：</strong> {guidance.action}</Typography>
        </Alert>
        <Button variant="outlined" startIcon={<RefreshIcon />} onClick={() => void loadDetail()}>重新加载</Button>
      </Box>
    );
  }

  const rawEvidence = evidencePayload;
  const rawInference = inferencePayload;
  const sanitizedEvidence = sanitizeQ3Evidence(rawEvidence);
  const sanitizedInference = sanitizeQ3Inference(rawInference);
  const evidence = sanitizedEvidence.value as Q3PreprocessedEvidence;
  const inference = sanitizedInference.value as Q3WhatDoIHaveInferenceView | null;
  const llmTrace = tracePayload;
  const hasStructuredSnapshot = Boolean(rawEvidence);
  const detailWarnings = [...sanitizedEvidence.warnings, ...sanitizedInference.warnings];
  const showIncompleteAlert = !rawEvidence || !rawInference;
  const providerName = String(tracePayload?.provider_name || rawPayload?.llm_trace_payload?.provider_name || "");
  const traceId = String(rawPayload?.trace_id || "");
  const toolId = String(rawPayload?.tool_id || `nine_questions.${qId}`);
  const pageStatus = String(summary?.status || modulesPayload?.status?.status || "partial");
  const mountedPlugins = Array.isArray(rawPayload?.mounted_plugins) ? rawPayload.mounted_plugins : [];
  const executionDiagnosis = rawPayload?.context_updates?.q3_execution_diagnosis || null;
  const recoveryPlan = executionDiagnosis?.recovery_plan || null;

  return (
    <Box data-testid="q3-detail-root">
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Box>
          <Typography variant="h4" gutterBottom>{getQuestionDisplayLabel(qId)} 正式审计页</Typography>
          <Typography variant="body2" color="text.secondary">Workspace Assets & Tooling Audit (Independent API GET /nine-questions/q3)</Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <NineQuestionRerunButton qId={qId} onCompleted={loadDetail} />
          <NineQuestionWorkflowNavButton qId={qId} />
          <Button component={RouterLink} to="/console/nine-questions/q3/test" variant="contained" color="warning" data-testid="q3-sandbox-nav-button">进入独立沙箱测试</Button>
        </Stack>
      </Stack>

      <NineQuestionIntroCard questionId="q3" />
      {executionDiagnosis ? (
        <Alert severity={executionDiagnosis.authenticity_status === "completed" ? "success" : "warning"} sx={{ mb: 2 }}>
          <AlertTitle>
            {executionDiagnosis.authenticity_status === "completed" ? "Q3 真实性状态：已验证完成" : "Q3 真实性状态：降级/部分失败"}
          </AlertTitle>
          <Typography variant="body2">
            {String(executionDiagnosis.diagnosis_message || "当前没有诊断说明。")}
          </Typography>
          <Typography variant="body2" sx={{ mt: 1 }}>
            {executionDiagnosis.used_fallback ? "本次使用了 fallback，资产盘点不是完整真实链。" : "本次未使用 fallback。"}
          </Typography>
        </Alert>
      ) : null}
      {recoveryPlan ? (
        <Alert severity="info" sx={{ mb: 2 }} data-testid="q3-recovery-plan">
          <AlertTitle>Q3 失败恢复计划</AlertTitle>
          <NineQuestionRecoveryActions qId={qId} recoveryPlan={recoveryPlan} onCompleted={loadDetail} />
        </Alert>
      ) : null}
      {showIncompleteAlert ? (
        <Alert severity="info" sx={{ mb: 3 }}>
          Q3 当前只拿到了部分分区数据，页面已按可用结果降级展示。
        </Alert>
      ) : null}
      <NineQuestionAnswerTable questionId={qId} inference={inference} result={rawPayload?.result} />

      <NineQuestionSectionBoundary title="Q3 数据详情">
        {sectionErrors.summary ? <Alert severity="warning" sx={{ mb: 2 }}>{sectionErrors.summary}</Alert> : null}
        {sectionErrors.evidence ? <Alert severity="warning" sx={{ mb: 2 }}>{sectionErrors.evidence}</Alert> : null}
        {sectionErrors.inference ? <Alert severity="warning" sx={{ mb: 2 }}>{sectionErrors.inference}</Alert> : null}
        <Q3DataTabs
          evidence={hasStructuredSnapshot ? evidence : null}
          inference={inference}
        />
      </NineQuestionSectionBoundary>
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Stack direction="row" spacing={1} sx={{ mb: 2 }} useFlexGap flexWrap="wrap">
            <Chip label={pageStatus} color="primary" data-testid="q3-cache-status-chip" />
            {providerName ? <Chip label={providerName} variant="outlined" /> : null}
            <Chip label={toolId} variant="outlined" sx={{ fontFamily: "monospace" }} />
            {traceId ? <Chip label={`trace: ${traceId}`} variant="outlined" sx={{ fontFamily: "monospace" }} data-testid="q3-trace-chip" /> : null}
          </Stack>
          <MountedPluginsZone plugins={mountedPlugins} />

          <Typography variant="h6" gutterBottom sx={{ mt: 2, fontWeight: "bold" }}>Q3 角色推断结构化证据</Typography>
          {!hasStructuredSnapshot ? (
            <Alert severity="warning" sx={{ mb: 2 }}>
              当前没有可用的结构化证据，以下区域保留布局并显示可恢复的空态。
            </Alert>
          ) : null}
          <NineQuestionSectionBoundary title="Q3 结构化证据">
            {sectionErrors.modules ? <Alert severity="warning" sx={{ mb: 2 }}>{sectionErrors.modules}</Alert> : null}
            <Q3EvidencePanel
              evidence={evidence}
              inference={inference}
              providerName={providerName || null}
              elapsedMs={tracePayload?.elapsed_ms || rawPayload?.llm_trace_payload?.elapsed_ms || 0}
              trace={llmTrace as LLMTracePayloadView}
            />
          </NineQuestionSectionBoundary>
        </CardContent>
      </Card>

      <NineQuestionIntegrationStatusCard qId={qId} modulesPayload={modulesPayload} />

      {detailWarnings.length > 0 || !rawEvidence || !rawInference ? (
        <NineQuestionRawPayloadCard
          title="Q3 原始字段诊断"
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

      <NineQuestionSectionBoundary title="Q3 Trace">
        {sectionErrors.trace ? <Alert severity="warning" sx={{ mb: 2 }}>{sectionErrors.trace}</Alert> : null}
        <LLMTracePanel trace={llmTrace as LLMTracePayloadView} />
      </NineQuestionSectionBoundary>
    </Box>
  );
}
