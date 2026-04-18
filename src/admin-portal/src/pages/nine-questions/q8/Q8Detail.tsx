import React, { useEffect, useState } from "react";
import {
  Alert,
  AlertTitle,
  Box,
  Button,
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
  Q8PreprocessedEvidence,
  Q8WhatShouldIDoNowInferenceView,
} from "../nineQuestionsApi";
import Q8EvidencePanel from "../../../components/Q8EvidencePanel";
import LLMTracePanel from "../../../components/LLMTracePanel";
import NineQuestionIntroCard from "../../../components/NineQuestionIntroCard";
import Q8DataTabs from "../../../components/Q8DataTabs";
import NineQuestionIncompleteResultAlert from "../../../components/NineQuestionIncompleteResultAlert";
import NineQuestionRerunButton from "../../../components/NineQuestionRerunButton";

function resolveErrorGuidance(errMsg: string): { title: string; action: string } {
  if (errMsg.includes("No active session") || errMsg.includes("没有活动 session")) {
    return {
      title: "当前没有活动的 Session",
      action: "请先运行一次完整的九问推演流程，完成后刷新此页即可查看最终决策结果。",
    };
  }
  if (errMsg.includes("尚无快照记录")) {
    return {
      title: "Q8 尚未产生终局决策",
      action: "主决策引擎快照为空。可能由于前置认知层（Q1-Q7）存在阻塞或尚未完成。请在 Zentex Brain Runtime 中重新触发完整推演。",
    };
  }
  if (errMsg.includes("状态机未挂载") || errMsg.includes("503")) {
    return {
      title: "核心决策引擎未就绪",
      action: "NineQuestionState 未挂载。Q8 作为九问终局决策对状态机完整性要求极高。请确认 Zentex Brain Runtime 启动状态后再刷新。",
    };
  }
  return {
    title: "加载决策数据失败",
    action: "请检查网络或确认后台服务状态后刷新重试。",
  };
}

export const Q8Detail: React.FC = () => {
  const qId = "q8";
  const [question, setQuestion] = useState<NineQuestionItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [workspaceTaskGoals, setWorkspaceTaskGoals] = useState<string[]>([]);

  const loadDetail = async () => {
    setLoading(true);
    setError(null);
    try {
      // 物理接口绑定: GET /api/web/nine-questions/q8
      const item = await fetchNineQuestionDetail(qId);
      setQuestion(item);
      
      // Load workspace task goals from localStorage
      const currentWorkspaceId = localStorage.getItem("currentWorkspaceId");
      if (currentWorkspaceId) {
        try {
          const response = await fetch(
            `http://127.0.0.1:8000/api/web/workspaces/${currentWorkspaceId}`
          );
          if (response.ok) {
            const workspace = await response.json();
            if (workspace.task_goals) {
              try {
                const goals = JSON.parse(workspace.task_goals);
                setWorkspaceTaskGoals(Array.isArray(goals) ? goals : []);
              } catch {
                setWorkspaceTaskGoals([]);
              }
            }
          }
        } catch (err) {
          console.warn("Failed to load workspace task goals:", err);
        }
      }
    } catch (err: any) {
      setError(err?.message || "加载 Q8 详情失败");
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
      <Typography variant="body2" color="text.secondary">正在加载 Q8 终局决策审计数据...</Typography>
    </Box>
  );

  if (error) {
    const guidance = resolveErrorGuidance(error);
    return (
      <Box sx={{ p: 3 }} data-testid="q8-error-boundary">
        <Alert severity="error" sx={{ mb: 2 }}>
          <AlertTitle>{guidance.title}</AlertTitle>
          <Typography variant="body2"><strong>建议操作：</strong> {guidance.action}</Typography>
        </Alert>
        <Button variant="outlined" startIcon={<RefreshIcon />} onClick={() => void loadDetail()} data-testid="q8-retry-button">重新加载</Button>
      </Box>
    );
  }

  if (!question) return <Alert severity="warning">未能找到 Q8 终局决策报告记录</Alert>;

  const evidence = question.preprocessed_evidence as Q8PreprocessedEvidence;
  const inference = question.inference_result as Q8WhatShouldIDoNowInferenceView;
  const llmTrace = question.llm_trace_payload;
  const hasStructuredSnapshot = Boolean(evidence && inference);

  return (
    <Box data-testid="q8-detail-root" sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0 }}>
        <Box>
          <Typography variant="h4" fontWeight="bold" gutterBottom>
            {getQuestionDisplayLabel(qId)} 正式审计页
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Final Objective Arbitration & Task Orchestration (Independent API GET /nine-questions/q8)
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <NineQuestionRerunButton qId={qId} onCompleted={loadDetail} />
          <Button
            component={RouterLink}
            to={`/console/nine-questions/${qId}/test`}
            variant="contained"
            color="warning"
            data-testid="q8-sandbox-nav-button"
          >
            进入独立沙箱测试
          </Button>
        </Stack>
      </Stack>

      {hasStructuredSnapshot ? (
        <>
          <NineQuestionIntroCard questionId={qId} />
          <Q8DataTabs
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
      {/* Workspace Task Goals */}
      {workspaceTaskGoals.length > 0 && (
        <Alert severity="info" variant="outlined" sx={{ backgroundColor: "#e3f2fd" }}>
          <Typography variant="h6" sx={{ mb: 1, fontWeight: "bold" }}>
            🎯 当前工作区的任务目标
          </Typography>
          <Stack spacing={1}>
            {workspaceTaskGoals.map((goal, index) => (
              <Typography key={index} variant="body2" sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <span sx={{ fontWeight: "bold" }}>{index + 1}.</span> {goal}
              </Typography>
            ))}
          </Stack>
        </Alert>
      )}

      <Box sx={{ mb: 0 }}>
        <Stack direction="row" spacing={1} sx={{ mb: 2 }} useFlexGap flexWrap="wrap">
          <Chip label={question.cache_status} color="primary" data-testid="q8-cache-status-chip" />
          <Chip label={question.provider_name} variant="outlined" />
          <Chip label={question.tool_id} variant="outlined" sx={{ fontFamily: "monospace" }} />
          {question.trace_id && <Chip label={`trace: ${question.trace_id}`} variant="outlined" sx={{ fontFamily: "monospace" }} data-testid="q8-trace-chip" />}
        </Stack>
      </Box>

      {hasStructuredSnapshot ? (
        <Q8EvidencePanel
          evidence={evidence}
          inference={inference}
          providerName={question.provider_name || null}
          elapsedMs={llmTrace?.elapsed_ms || 0}
        />
      ) : null}

      <LLMTracePanel trace={llmTrace as LLMTracePayloadView} />
    </Box>
  );
};

export default Q8Detail;
