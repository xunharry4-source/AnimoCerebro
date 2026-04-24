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
  fetchNineQuestionDetail,
  fetchNineQuestionModules,
  getQuestionDisplayLabel,
  LLMTracePayloadView,
  NineQuestionItem,
  Q9PreprocessedEvidence,
  Q9ActionPostureInferenceView,
} from "../nineQuestionsApi";
import Q9EvidencePanel from "../../../components/Q9EvidencePanel";
import LLMTracePanel from "../../../components/LLMTracePanel";
import NineQuestionIntroCard from "../../../components/NineQuestionIntroCard";
import Q9DataTabs from "../../../components/Q9DataTabs";
import NineQuestionIncompleteResultAlert from "../../../components/NineQuestionIncompleteResultAlert";
import NineQuestionRerunButton from "../../../components/NineQuestionRerunButton";
import NineQuestionWorkflowNavButton from "../../../components/NineQuestionWorkflowNavButton";
import NineQuestionRecoveryActions from "../../../components/NineQuestionRecoveryActions";
import NineQuestionIntegrationStatusCard from "../../../components/NineQuestionIntegrationStatusCard";
import { sanitizeQ9Evidence, sanitizeQ9Inference } from "../detailSafeData";

function resolveErrorGuidance(errMsg: string): { title: string; action: string } {
  if (errMsg.includes("No active session") || errMsg.includes("没有活动 session")) {
    return {
      title: "当前还没有可读取的九问快照",
      action: "请先运行一次完整的九问推演流程，完成后再回到这个监控页刷新。",
    };
  }
  if (errMsg.includes("尚无快照记录")) {
    return {
      title: "Q9 尚未产生姿态定调",
      action: "该问题的推断快照为空。可能由于前置认知环（Q1-Q8）存在阻塞。请在 Zentex Brain Runtime 中重新触发推演。",
    };
  }
  if (errMsg.includes("状态机未挂载") || errMsg.includes("503")) {
    return {
      title: "后端推演引擎未就绪",
      action: "NineQuestionState 未挂载。请检查 Zentex Brain Runtime 启动状态，确认服务初始化后再刷新。",
    };
  }
  return {
    title: "加载数据失败",
    action: "请检查网络或确认后台服务状态后刷新重试。",
  };
}

export default function Q9Detail() {
  const qId = "q9";
  const [question, setQuestion] = useState<NineQuestionItem | null>(null);
  const [modulesPayload, setModulesPayload] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDetail = async () => {
    setLoading(true);
    setError(null);
    try {
      const [item, modules] = await Promise.all([
        fetchNineQuestionDetail(qId),
        fetchNineQuestionModules(qId),
      ]);
      setQuestion(item);
      setModulesPayload(modules);
    } catch (err: any) {
      setError(err?.message || "加载 Q9 详情失败");
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
      <Typography variant="body2" color="text.secondary">正在加载 Q9 姿态审计数据...</Typography>
    </Box>
  );

  if (error) {
    const guidance = resolveErrorGuidance(error);
    return (
      <Box sx={{ p: 3 }} data-testid="q9-error-boundary">
        <Alert severity="error" sx={{ mb: 2 }}>
          <AlertTitle>{guidance.title}</AlertTitle>
          <Typography variant="body2"><strong>建议操作：</strong> {guidance.action}</Typography>
        </Alert>
        <Button variant="outlined" startIcon={<RefreshIcon />} onClick={() => void loadDetail()} data-testid="q9-retry-button">重新加载</Button>
      </Box>
    );
  }

  if (!question) return <Alert severity="warning">未能找到 Q9 记录。</Alert>;

  const sanitizedEvidence = sanitizeQ9Evidence(question.preprocessed_evidence);
  const sanitizedInference = sanitizeQ9Inference(question.inference_result);
  const evidence = sanitizedEvidence.value as Q9PreprocessedEvidence;
  const inference = sanitizedInference.value as Q9ActionPostureInferenceView | null;
  const llmTrace = question.llm_trace_payload;
  const hasStructuredSnapshot = Boolean(question.preprocessed_evidence);
  const executionDiagnosis = question.context_updates?.q9_execution_diagnosis || null;
  const recoveryPlan = executionDiagnosis?.recovery_plan || null;
  const detailWarnings = [...sanitizedEvidence.warnings, ...sanitizedInference.warnings];

  return (
    <Box data-testid="q9-detail-root" sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0 }}>
        <Box>
          <Typography variant="h4" fontWeight="bold" gutterBottom>{getQuestionDisplayLabel(qId)} 正式审计页</Typography>
          <Typography variant="body2" color="text.secondary">Self-Model Pressure & Action Posture Audit (Independent API GET /nine-questions/q9)</Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <NineQuestionRerunButton qId={qId} onCompleted={loadDetail} />
          <NineQuestionWorkflowNavButton qId={qId} />
          <Button
            component={RouterLink}
            to={`/console/nine-questions/${qId}/test`}
            variant="contained"
            color="warning"
            data-testid="q9-sandbox-nav-button"
          >
            进入独立沙箱测试
          </Button>
        </Stack>
      </Stack>

      {executionDiagnosis ? (
        <Alert severity={executionDiagnosis.authenticity_status === "completed" ? "success" : "warning"}>
          <AlertTitle>
            {executionDiagnosis.authenticity_status === "completed" ? "Q9 真实性状态：已验证完成" : "Q9 真实性状态：降级/部分失败"}
          </AlertTitle>
          <Typography variant="body2">{String(executionDiagnosis.diagnosis_message || "当前没有诊断说明。")}</Typography>
        </Alert>
      ) : null}
      {recoveryPlan ? (
        <Alert severity="info" data-testid="q9-recovery-plan">
          <AlertTitle>Q9 失败恢复计划</AlertTitle>
          <NineQuestionRecoveryActions qId={qId} recoveryPlan={recoveryPlan} onCompleted={loadDetail} />
        </Alert>
      ) : null}
      {detailWarnings.length > 0 ? (
        <Alert severity="warning">
          <AlertTitle>Q9 数据已按降级结构清洗</AlertTitle>
          <Typography variant="body2">{detailWarnings.join(" ")}</Typography>
        </Alert>
      ) : null}


      {hasStructuredSnapshot ? (
        <>
          <NineQuestionIntroCard questionId="q9" />
          <Q9DataTabs
            evidence={evidence as any}
            inference={inference as any}
          />
        </>
      ) : (
        <NineQuestionIncompleteResultAlert
          questionId={qId}
          result={question.result}
          contextUpdates={question.context_updates}
        />
      )}
      <Card variant="outlined">
        <CardContent>
          <Stack direction="row" spacing={1} sx={{ mb: 2 }} useFlexGap flexWrap="wrap">
            <Chip label={question.cache_status} color="primary" data-testid="q9-cache-status-chip" />
            <Chip label={question.provider_name} variant="outlined" />
            <Chip label={question.tool_id} variant="outlined" sx={{ fontFamily: "monospace" }} />
            {question.trace_id && <Chip label={`trace: ${question.trace_id}`} variant="outlined" sx={{ fontFamily: "monospace" }} data-testid="q9-trace-chip" />}
          </Stack>

          <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: "bold", mt: 2 }}>
            结构化行动姿态证据 (Self-Model & Posture)
          </Typography>

          {hasStructuredSnapshot ? (
            <Q9EvidencePanel
              evidence={evidence}
              inference={inference}
              providerName={question.provider_name || null}
              elapsedMs={llmTrace?.elapsed_ms || 0}
            />
          ) : <Alert severity="warning">暂无结构化行动姿态证据。</Alert>}
        </CardContent>
      </Card>

      <NineQuestionIntegrationStatusCard qId={qId} modulesPayload={modulesPayload} />
      
      <LLMTracePanel trace={llmTrace as LLMTracePayloadView} />
    </Box>
  );
}
