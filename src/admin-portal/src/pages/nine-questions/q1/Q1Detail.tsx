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
import NineQuestionIntroCard from "../../../components/NineQuestionIntroCard";
import Q1DataTabs from "../../../components/Q1DataTabs";

// Maps HTTP error context → human-readable guidance
function resolveErrorGuidance(errMsg: string, t: (key: string) => string): { title: string; action: string } {
  if (errMsg.includes("No active session") || errMsg.includes("没有活动 session")) {
    return {
      title: t("nineQuestions.q1.noActiveSession"),
      action: t("nineQuestions.q1.actionRunDeduction"),
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

export default function Q1Detail() {
  const { t } = useTranslation();
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

  if (!question) {
    return (
      <Alert severity="warning">
        {t("nineQuestions.q1.noRecord")}
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
            {getQuestionDisplayLabel(qId)} {t("nineQuestions.q1.productionAudit")}
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
          {t("nineQuestions.q1.enterSandbox")}
        </Button>
      </Stack>

      {/* 问题介绍栏目 */}
      <NineQuestionIntroCard questionId={qId} />

      {/* Q1 实际数据详情 Tab 面板 */}
      <Q1DataTabs 
        evidence={evidence as any} 
        inference={inference as any} 
      />


      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          {/* 状态芯片阵列 — 主领域 / 次领域 / 插件 */}
          <Stack direction="row" spacing={1} sx={{ mb: 2 }} useFlexGap flexWrap="wrap">
            <Chip
              label={question.cache_status || t("nineQuestions.evidencePanels.unknown")}
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
          <MountedPluginsZone plugins={question.mounted_plugins || []} />

          <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: "bold", mt: 2 }}>
            {t("nineQuestions.q1.structuredEvidence")}
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
              {t("nineQuestions.q1.noStructuredEvidence")}
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
