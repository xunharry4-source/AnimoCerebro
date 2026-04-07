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
  Q1PreprocessedEvidence,
  WorkspaceDomainInferenceView,
  LLMTracePayloadView,
} from "../nineQuestionsApi";
import Q1EvidencePanel from "../../../components/Q1EvidencePanel";
import LLMTracePanel from "../../../components/LLMTracePanel";
import MountedPluginsZone from "../../../components/MountedPluginsZone";
import Q1UpgradePanel from "../../../components/Q1UpgradePanel";

// Maps HTTP error context → human-readable guidance
function resolveErrorGuidance(errMsg: string): { title: string; action: string } {
  if (errMsg.includes("No active session") || errMsg.includes("没有活动 session")) {
    return {
      title: "当前没有活动的 Session",
      action: "请先运行一次完整的九问推演流程，完成后刷新此页即可查看结果。",
    };
  }
  if (errMsg.includes("尚无快照记录")) {
    return {
      title: "Q1 尚未产生推断结果",
      action:
        "该问题的推演快照为空。请在 Zentex Brain Runtime 中触发一次全量九问推演，完成后再回到此页查看。",
    };
  }
  if (errMsg.includes("状态机未挂载") || errMsg.includes("503")) {
    return {
      title: "后端推演引擎未就绪",
      action:
        "NineQuestionState 未挂载到运行时。请检查 Zentex Brain Runtime 的启动状态，确认服务已正确初始化后再刷新。",
    };
  }
  if (errMsg.includes("NetworkError") || errMsg.includes("Failed to fetch")) {
    return {
      title: "网络连接失败",
      action: "无法连接到后台服务。请检查网络连接或确认 dev server 正在运行后重试。",
    };
  }
  return {
    title: "加载数据失败",
    action: "请刷新页面重试。若问题持续出现，请检查后台服务日志以获取详细信息。",
  };
}

export default function Q1Detail() {
  const qId = "q1";
  const [question, setQuestion] = useState<NineQuestionItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDetail = async () => {
    setLoading(true);
    setError(null);
    try {
      // 直接调用独立接口 GET /api/web/nine-questions/q1
      // 不再依赖聚合大报告 /latest-report
      const item = await fetchNineQuestionDetail(qId);
      setQuestion(item);
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
          正在从生产环境拉取 Q1 快照…
        </Typography>
      </Box>
    );
  }

  // ——— 人话降级熔断区 ———
  if (error) {
    const guidance = resolveErrorGuidance(error);
    return (
      <Box sx={{ p: 3 }} data-testid="q1-error-boundary">
        <Alert severity="error" sx={{ mb: 2 }}>
          <AlertTitle>{guidance.title}</AlertTitle>
          <Typography variant="body2" sx={{ mt: 0.5 }}>
            <strong>下一步：</strong> {guidance.action}
          </Typography>
        </Alert>
        <Button
          variant="outlined"
          startIcon={<RefreshIcon />}
          onClick={() => void loadDetail()}
          data-testid="q1-retry-button"
        >
          重新加载
        </Button>
      </Box>
    );
  }

  if (!question) {
    return (
      <Alert severity="warning">
        Q1 尚无推断记录，请先运行完整的九问推演流程后再查看此页。
      </Alert>
    );
  }

  const evidence = question.preprocessed_evidence;
  const inference = question.inference_result;
  const llmTracePayload = question.llm_trace_payload;
  const q1Upgrade = question.q1_llm_upgrade;

  return (
    <Box data-testid="q1-detail-root">
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 3 }}>
        <Box>
          <Typography variant="h4" gutterBottom>
            {getQuestionDisplayLabel(qId)} 正式审计页
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Production Snapshot: Workspace &amp; Environment Audit（只读，数据来源 GET /nine-questions/q1）
          </Typography>
        </Box>
        <Button
          component={RouterLink}
          to={`/console/nine-questions/${qId}/test`}
          variant="contained"
          color="warning"
          data-testid="q1-sandbox-nav-button"
        >
          进入独立沙箱测试
        </Button>
      </Stack>

      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          {/* 状态芯片阵列 — 主领域 / 次领域 / 插件 */}
          <Stack direction="row" spacing={1} sx={{ mb: 2 }} useFlexGap flexWrap="wrap">
            <Chip
              label={question.cache_status || "未知"}
              color="primary"
              data-testid="q1-cache-status-chip"
            />
            <Chip label={question.provider_name || "-"} variant="outlined" />
            <Chip
              label={question.tool_id}
              variant="outlined"
              sx={{ fontFamily: "monospace" }}
            />
            {question.trace_id && (
              <Chip
                label={`trace: ${question.trace_id}`}
                variant="outlined"
                sx={{ fontFamily: "monospace" }}
                data-testid="q1-trace-chip"
              />
            )}
            {/* 推断主领域 Chip */}
            {(inference as WorkspaceDomainInferenceView)?.primary_domain && (
              <Chip
                label={`主领域: ${(inference as WorkspaceDomainInferenceView).primary_domain}`}
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
          <MountedPluginsZone plugins={question.mounted_plugins || []} />

          <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: "bold", mt: 2 }}>
            结构化分层证据 (Zentex G31A)
          </Typography>

          {/* 主证据面板 - Q1EvidencePanel 内部的 Accordion 均默认折叠 */}
          {evidence ? (
            <Q1EvidencePanel
              evidence={evidence as Q1PreprocessedEvidence}
              inference={inference as WorkspaceDomainInferenceView}
              providerName={question.provider_name ?? null}
              elapsedMs={question.llm_trace_payload?.elapsed_ms ?? 0}
            />
          ) : (
            <Alert severity="warning">
              暂无结构化证据数据。当前 session 可能尚未完成 Q1 推演，请先运行九问流程。
            </Alert>
          )}
        </CardContent>
      </Card>

      <Box sx={{ mb: 3 }}>
        <Q1UpgradePanel upgrade={q1Upgrade} />
      </Box>

      {/* LLM 交互溯源区 - LLMTracePanel 内部自带 Accordion 默认折叠 */}
      <LLMTracePanel trace={llmTracePayload as LLMTracePayloadView} />
    </Box>
  );
}
