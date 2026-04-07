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
  Q2PreprocessedEvidence,
  Q2WhoAmIInferenceView,
  LLMTracePayloadView,
} from "../nineQuestionsApi";
import Q2EvidencePanel from "../../../components/Q2EvidencePanel";
import MountedPluginsZone from "../../../components/MountedPluginsZone";
import LLMTracePanel from "../../../components/LLMTracePanel";

function resolveErrorGuidance(errMsg: string): { title: string; action: string } {
  if (errMsg.includes("No active session") || errMsg.includes("没有活动 session")) {
    return {
      title: "当前没有活动的 Session",
      action: "请先运行一次完整的九问推演流程，完成后刷新此页即可查看结果。",
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

export default function Q2Detail() {
  const qId = "q2";
  const [question, setQuestion] = useState<NineQuestionItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDetail = async () => {
    setLoading(true);
    setError(null);
    try {
      const item = await fetchNineQuestionDetail(qId);
      setQuestion(item);
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

  if (!question) return <Alert severity="warning">未找到 Q2 记录。</Alert>;

  const evidence = question.preprocessed_evidence as Q2PreprocessedEvidence;
  const inference = question.inference_result as Q2WhoAmIInferenceView;
  const llmTrace = question.llm_trace_payload;

  return (
    <Box data-testid="q2-detail-root">
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Box>
          <Typography variant="h4" gutterBottom>{getQuestionDisplayLabel(qId)} 正式审计页</Typography>
          <Typography variant="body2" color="text.secondary">Mission Continuity & Role Identity Audit（独立接口 GET /nine-questions/q2）</Typography>
        </Box>
        <Button component={RouterLink} to="/console/nine-questions/q2/test" variant="contained" color="warning" data-testid="q2-sandbox-nav-button">进入独立沙箱测试</Button>
      </Stack>

      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Stack direction="row" spacing={1} sx={{ mb: 2 }} useFlexGap flexWrap="wrap">
            <Chip label={question.cache_status} color="primary" data-testid="q2-cache-status-chip" />
            <Chip label={question.provider_name} variant="outlined" />
            <Chip label={question.tool_id} variant="outlined" sx={{ fontFamily: "monospace" }} />
            {question.trace_id && <Chip label={`trace: ${question.trace_id}`} variant="outlined" sx={{ fontFamily: "monospace" }} data-testid="q2-trace-chip" />}
            {inference?.role_profile?.active_role && (
              <Chip label={`活跃角色: ${inference.role_profile.active_role}`} color="secondary" data-testid="q2-active-role-chip" />
            )}
          </Stack>

          <MountedPluginsZone plugins={question.mounted_plugins || []} />

          <Typography variant="h6" gutterBottom sx={{ mt: 2 }}>身份内核与使命连续性证明 (Evidence)</Typography>
          {evidence ? (
            <Q2EvidencePanel
              evidence={evidence}
              inference={inference}
              providerName={question.provider_name || null}
              elapsedMs={question.llm_trace_payload?.elapsed_ms || 0}
            />
          ) : <Alert severity="warning">无结构化证据。</Alert>}
        </CardContent>
      </Card>

      <LLMTracePanel trace={llmTrace as LLMTracePayloadView} />
    </Box>
  );
}
