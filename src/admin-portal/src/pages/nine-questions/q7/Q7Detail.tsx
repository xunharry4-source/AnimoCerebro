import React, { useEffect, useState } from "react";
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
  getQuestionDisplayLabel,
  LLMTracePayloadView,
  NineQuestionItem,
  Q7PreprocessedEvidence,
  Q7AlternativeStrategyInferenceView,
} from "../nineQuestionsApi";
import Q7EvidencePanel from "../../../components/Q7EvidencePanel";
import MountedPluginsZone from "../../../components/MountedPluginsZone";
import LLMTracePanel from "../../../components/LLMTracePanel";
import NineQuestionIntroCard from "../../../components/NineQuestionIntroCard";

function resolveErrorGuidance(errMsg: string): { title: string; action: string } {
  if (errMsg.includes("No active session") || errMsg.includes("没有活动 session")) {
    return {
      title: "当前没有活动的 Session",
      action: "请先运行一次完整的九问推演流程，完成后刷新此页即可查看结果。",
    };
  }
  if (errMsg.includes("尚无快照记录")) {
    return {
      title: "Q7 尚未产生推断结果",
      action: "该问题的推断快照为空。降级方案审计可能由于前置认知环失败或未触发。请在 Zentex Brain Runtime 中重新触发推演。",
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

export const Q7Detail: React.FC = () => {
  const qId = "q7";
  const [question, setQuestion] = useState<NineQuestionItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDetail = async () => {
    setLoading(true);
    setError(null);
    try {
      // 物理接口绑定: GET /api/web/nine-questions/q7
      const item = await fetchNineQuestionDetail(qId);
      setQuestion(item);
    } catch (err: any) {
      setError(err?.message || "加载 Q7 详情失败");
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
      <Typography variant="body2" color="text.secondary">正在加载 Q7 降级审计数据...</Typography>
    </Box>
  );

  if (error) {
    const guidance = resolveErrorGuidance(error);
    return (
      <Box sx={{ p: 3 }} data-testid="q7-error-boundary">
        <Alert severity="error" sx={{ mb: 2 }}>
          <AlertTitle>{guidance.title}</AlertTitle>
          <Typography variant="body2"><strong>建议操作：</strong> {guidance.action}</Typography>
        </Alert>
        <Button variant="outlined" startIcon={<RefreshIcon />} onClick={() => void loadDetail()} data-testid="q7-retry-button">重新加载</Button>
      </Box>
    );
  }

  if (!question) return <Alert severity="warning">未能找到 Q7 报告记录</Alert>;

  const evidence = question.preprocessed_evidence as Q7PreprocessedEvidence;
  const inference = question.inference_result as Q7AlternativeStrategyInferenceView;
  const llmTrace = question.llm_trace_payload;

  return (
    <Box data-testid="q7-detail-root" sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0 }}>
        <Box>
          <Typography variant="h4" fontWeight="bold" gutterBottom>
            {getQuestionDisplayLabel(qId)} 正式审计页
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Degradation Strategy & Fallback Planning (Independent API GET /nine-questions/q7)
          </Typography>
        </Box>
        <Button
          component={RouterLink}
          to={`/console/nine-questions/${qId}/test`}
          variant="contained"
          color="warning"
          data-testid="q7-sandbox-nav-button"
        >
          进入独立沙箱测试
        </Button>
      </Stack>


      {/* 问题介绍栏目 */}
      <NineQuestionIntroCard questionId="q7" />

      <Card variant="outlined">
        <CardContent>
          <Stack direction="row" spacing={1} sx={{ mb: 2 }} useFlexGap flexWrap="wrap">
            <Chip label={question.cache_status} color="primary" data-testid="q7-cache-status-chip" />
            <Chip label={question.provider_name} variant="outlined" />
            <Chip label={question.tool_id} variant="outlined" sx={{ fontFamily: "monospace" }} />
            {question.trace_id && <Chip label={`trace: ${question.trace_id}`} variant="outlined" sx={{ fontFamily: "monospace" }} data-testid="q7-trace-chip" />}
          </Stack>

          <MountedPluginsZone plugins={question.mounted_plugins || []} />
        </CardContent>
      </Card>

      {evidence && (
        <Q7EvidencePanel
          evidence={evidence}
          inference={inference}
          providerName={question.provider_name || null}
          elapsedMs={llmTrace?.elapsed_ms || 0}
        />
      )}

      <LLMTracePanel trace={llmTrace as LLMTracePayloadView} />
    </Box>
  );
};

export default Q7Detail;
