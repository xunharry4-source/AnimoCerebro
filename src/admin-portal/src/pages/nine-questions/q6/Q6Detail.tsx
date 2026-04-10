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
  Q6PreprocessedEvidence,
} from "../nineQuestionsApi";
import Q6EvidencePanel from "../../../components/Q6EvidencePanel";
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
      title: "Q6 尚未产生推断结果",
      action: "该问题的推断快照为空。可能由于前置认知环失败或未触发。请在 Zentex Brain Runtime 中重新触发推演。",
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

export const Q6Detail: React.FC = () => {
  const qId = "q6";
  const [question, setQuestion] = useState<NineQuestionItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDetail = async () => {
    setLoading(true);
    setError(null);
    try {
      // 物理接口绑定: GET /api/web/nine-questions/q6
      const item = await fetchNineQuestionDetail(qId);
      setQuestion(item);
    } catch (err: any) {
      setError(err?.message || "加载 Q6 详情失败");
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
      <Typography variant="body2" color="text.secondary">正在加载 Q6 禁区审计数据...</Typography>
    </Box>
  );

  if (error) {
    const guidance = resolveErrorGuidance(error);
    return (
      <Box sx={{ p: 3 }} data-testid="q6-error-boundary">
        <Alert severity="error" sx={{ mb: 2 }}>
          <AlertTitle>{guidance.title}</AlertTitle>
          <Typography variant="body2"><strong>建议操作：</strong> {guidance.action}</Typography>
        </Alert>
        <Button variant="outlined" startIcon={<RefreshIcon />} onClick={() => void loadDetail()} data-testid="q6-retry-button">重新加载</Button>
      </Box>
    );
  }

  if (!question) return <Alert severity="warning">未能找到 Q6 报告记录</Alert>;

  const evidence = question.preprocessed_evidence as Q6PreprocessedEvidence;
  // Q6 使用 'conclusion' 字段作为 inference_result 的别名，但在标准化接口中统一为 inference_result
  const inference = question.inference_result;
  const llmTrace = question.llm_trace_payload;

  return (
    <Box data-testid="q6-detail-root" sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0 }}>
        <Box>
          <Typography variant="h4" fontWeight="bold" gutterBottom>
            {getQuestionDisplayLabel(qId)} 正式审计页
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Cognitive Redlines & Forbidden Boundaries (Independent API GET /nine-questions/q6)
          </Typography>
        </Box>
        <Button
          component={RouterLink}
          to={`/console/nine-questions/${qId}/test`}
          variant="contained"
          color="warning"
          data-testid="q6-sandbox-nav-button"
        >
          进入独立沙箱测试
        </Button>
      </Stack>


      {/* 问题介绍栏目 */}
      <NineQuestionIntroCard questionId="q6" />

      <Card variant="outlined">
        <CardContent>
          <Stack direction="row" spacing={1} sx={{ mb: 2 }} useFlexGap flexWrap="wrap">
            <Chip label={question.cache_status} color="primary" data-testid="q6-cache-status-chip" />
            <Chip label={question.provider_name} variant="outlined" />
            <Chip label={question.tool_id} variant="outlined" sx={{ fontFamily: "monospace" }} />
            {question.trace_id && <Chip label={`trace: ${question.trace_id}`} variant="outlined" sx={{ fontFamily: "monospace" }} data-testid="q6-trace-chip" />}
          </Stack>

          <MountedPluginsZone plugins={question.mounted_plugins || []} />
        </CardContent>
      </Card>

      {evidence && (
        <Q6EvidencePanel
          evidence={evidence}
          inference={inference as any}
          providerName={question.provider_name || null}
          elapsedMs={llmTrace?.elapsed_ms || 0}
        />
      )}

      <LLMTracePanel trace={llmTrace as LLMTracePayloadView} />
    </Box>
  );
};

export default Q6Detail;
