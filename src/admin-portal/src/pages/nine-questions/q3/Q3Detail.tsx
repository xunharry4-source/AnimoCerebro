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
  NineQuestionItem,
  fetchNineQuestionDetail,
  getQuestionDisplayLabel,
  Q3PreprocessedEvidence,
  Q3WhatDoIHaveInferenceView,
  LLMTracePayloadView,
} from "../nineQuestionsApi";
import Q3EvidencePanel from "../../../components/Q3EvidencePanel";
import MountedPluginsZone from "../../../components/MountedPluginsZone";
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
  const [question, setQuestion] = useState<NineQuestionItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDetail = async () => {
    setLoading(true);
    setError(null);
    try {
      // 绑定到独立接口 GET /api/web/nine-questions/q3
      const item = await fetchNineQuestionDetail(qId);
      setQuestion(item);
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
      <Typography variant="body2" color="text.secondary">正在加载 Q3 资源与工具审计数据...</Typography>
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

  if (!question) return <Alert severity="warning">未找到 Q3 记录。</Alert>;

  const evidence = question.preprocessed_evidence as Q3PreprocessedEvidence;
  const inference = question.inference_result as Q3WhatDoIHaveInferenceView;
  const llmTrace = question.llm_trace_payload;

  return (
    <Box data-testid="q3-detail-root">
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Box>
          <Typography variant="h4" gutterBottom>{getQuestionDisplayLabel(qId)} 正式审计页</Typography>
          <Typography variant="body2" color="text.secondary">Workspace Assets & Tooling Audit (Independent API GET /nine-questions/q3)</Typography>
        </Box>
        <Button component={RouterLink} to="/console/nine-questions/q3/test" variant="contained" color="warning" data-testid="q3-sandbox-nav-button">进入独立沙箱测试</Button>
      </Stack>


      {/* 问题介绍栏目 */}
      <NineQuestionIntroCard questionId="q3" />

      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Stack direction="row" spacing={1} sx={{ mb: 2 }} useFlexGap flexWrap="wrap">
            <Chip label={question.cache_status} color="primary" data-testid="q3-cache-status-chip" />
            <Chip label={question.provider_name} variant="outlined" />
            <Chip label={question.tool_id} variant="outlined" sx={{ fontFamily: "monospace" }} />
            {question.trace_id && <Chip label={`trace: ${question.trace_id}`} variant="outlined" sx={{ fontFamily: "monospace" }} data-testid="q3-trace-chip" />}
          </Stack>

          <MountedPluginsZone plugins={question.mounted_plugins || []} />

          <Typography variant="h6" gutterBottom sx={{ mt: 2, fontWeight: "bold" }}>结构化资源与工具证据 (Zentex G31A.Q3)</Typography>
          {evidence ? (
            <Q3EvidencePanel
              evidence={evidence}
              inference={inference}
              providerName={question.provider_name || null}
              elapsedMs={question.llm_trace_payload?.elapsed_ms || 0}
              trace={llmTrace as LLMTracePayloadView}
            />
          ) : <Alert severity="warning">无结构化证据数据。</Alert>}
        </CardContent>
      </Card>
    </Box>
  );
}
