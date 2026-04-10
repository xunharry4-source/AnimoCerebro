import { useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Stack,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { Link as RouterLink, useParams } from "react-router-dom";

import {
  ReportPayload,
  TraceDetail,
  fetchNineQuestionTrace,
  fetchNineQuestionsReport,
  fetchNineQuestionDetail,
  getQuestionDisplayLabel,
  getNineQuestionIntro,
} from "./nineQuestionsApi";
import Q1EvidencePanel from "../../components/Q1EvidencePanel";
import Q2EvidencePanel from "../../components/Q2EvidencePanel";
import LLMTracePanel from "../../components/LLMTracePanel";
import Q3EvidencePanel from "../../components/Q3EvidencePanel";
import Q4EvidencePanel from "../../components/Q4EvidencePanel";
import Q5EvidencePanel from "../../components/Q5EvidencePanel";
import { Q6EvidencePanel } from "../../components/Q6EvidencePanel";
import { Q7EvidencePanel } from "../../components/Q7EvidencePanel";
import Q8EvidencePanel from "../../components/Q8EvidencePanel";
import Q9EvidencePanel from "../../components/Q9EvidencePanel";
import {
  Q1PreprocessedEvidence,
  Q2PreprocessedEvidence,
  Q2WhoAmIInferenceView,
  Q3PreprocessedEvidence,
  Q3WhatDoIHaveInferenceView,
  Q4PreprocessedEvidence,
  Q4WhatCanIDoInferenceView,
  Q5PreprocessedEvidence,
  Q5WhatAmIAllowedToDoInferenceView,
  Q6PreprocessedEvidence,
  Q6ForbiddenZoneInferenceView,
  Q7PreprocessedEvidence,
  Q7AlternativeStrategyInferenceView,
  Q8PreprocessedEvidence,
  Q8WhatShouldIDoNowInferenceView,
  Q9ActionPostureInferenceView,
  Q9PreprocessedEvidence,
  WorkspaceDomainInferenceView,
  LLMTracePayloadView,
} from "./nineQuestionsApi";

export default function NineQuestionDetailPage() {
  const { t } = useTranslation();
  const { q_id: qId = "" } = useParams();
  const [report, setReport] = useState<ReportPayload | null>(null);
  const [traceDetail, setTraceDetail] = useState<TraceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    void loadDetail();
  }, [qId]);

  const loadDetail = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchNineQuestionDetail(qId);
      setReport({
        session_id: "loading",
        status: "ready",
        status_message: null,
        last_turn_id: "0",
        snapshot_version: 0,
        revision: 0,
        refreshed_at: null,
        last_refresh_reason: null,
        question_driver_refs: [],
        questions: [data],
      });
      if (data.trace_id) {
        const trace = await fetchNineQuestionTrace(data.trace_id);
        setTraceDetail(trace);
      } else {
        setTraceDetail(null);
      }
    } catch (err: any) {
      setError(err?.message || t("nineQuestions.fetchDetailError"));
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <CircularProgress />;
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  const question = report?.questions.find((item) => item.question_id === qId);
  if (!question) {
    return <Alert severity="error">{t("nineQuestions.notFound")}</Alert>;
  }

  // 获取当前问题的介绍信息
  const intro = getNineQuestionIntro(qId);
  const q1Evidence = question.question_id === "q1" ? question.preprocessed_evidence || traceDetail?.preprocessed_evidence : null;
  const q1Inference = question.question_id === "q1" ? question.inference_result || traceDetail?.inference_result : null;
  const q2Evidence = question.question_id === "q2" ? question.preprocessed_evidence || traceDetail?.preprocessed_evidence : null;
  const q2Inference = question.question_id === "q2" ? question.inference_result || traceDetail?.inference_result : null;
  const llmTracePayload =
    question.question_id === "q1" || question.question_id === "q2" || question.question_id === "q8" || question.question_id === "q9"
      ? question.llm_trace_payload || traceDetail?.llm_trace_payload
      : null;
  const q3Evidence = question.question_id === "q3" ? question.preprocessed_evidence || traceDetail?.preprocessed_evidence : null;
  const q3Inference = question.question_id === "q3" ? question.inference_result || traceDetail?.inference_result : null;
  const q4Evidence = question.question_id === "q4" ? question.preprocessed_evidence || traceDetail?.preprocessed_evidence : null;
  const q4Inference = question.question_id === "q4" ? question.inference_result || traceDetail?.inference_result : null;
  const q5Evidence = question.question_id === "q5" ? question.preprocessed_evidence || traceDetail?.preprocessed_evidence : null;
  const q5Inference = question.question_id === "q5" ? question.inference_result || traceDetail?.inference_result : null;
  const q6Evidence = question.question_id === "q6" ? question.preprocessed_evidence || traceDetail?.preprocessed_evidence : null;
  const q6Inference = question.question_id === "q6" ? question.inference_result || traceDetail?.inference_result : null;
  const q7Evidence = question.question_id === "q7" ? question.preprocessed_evidence || traceDetail?.preprocessed_evidence : null;
  const q7Inference = question.question_id === "q7" ? question.inference_result || traceDetail?.inference_result : null;
  const q8Evidence = question.question_id === "q8" ? question.preprocessed_evidence || traceDetail?.preprocessed_evidence : null;
  const q8Inference = question.question_id === "q8" ? question.inference_result || traceDetail?.inference_result : null;
  const q9Evidence = question.question_id === "q9" ? question.preprocessed_evidence || traceDetail?.preprocessed_evidence : null;
  const q9Inference = question.question_id === "q9" ? question.inference_result || traceDetail?.inference_result : null;

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 3 }}>
        <Box>
          <Typography variant="h4" gutterBottom>
            {getQuestionDisplayLabel(question.question_id)}
          </Typography>
          <Typography variant="h6" color="text.secondary">
            {question.title}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {question.summary}
          </Typography>
        </Box>
        <Button
          component={RouterLink}
          to={`/console/nine-questions/${question.question_id}/sandbox`}
          variant="contained"
          color="warning"
        >
          进入独立沙箱测试
        </Button>
      </Stack>

      {notice ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          {notice}
        </Alert>
      ) : null}

      {/* 问题介绍栏目 */}
      {intro && (
        <Card variant="outlined" sx={{ mb: 3, bgcolor: "primary.50", borderColor: "primary.main" }}>
          <CardContent>
            <Typography variant="h6" gutterBottom color="primary.main" fontWeight="bold">
              📖 问题说明
            </Typography>
            <Stack spacing={2}>
              <Box>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  🎯 目标
                </Typography>
                <Typography variant="body1">{intro.goal}</Typography>
              </Box>
              <Divider />
              <Box>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  📊 期望获得的数据
                </Typography>
                <Typography variant="body1">{intro.expectedData}</Typography>
              </Box>
              <Divider />
              <Box>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  ✨ 最终输出
                </Typography>
                <Typography variant="body1">{intro.finalOutput}</Typography>
              </Box>
            </Stack>
          </CardContent>
        </Card>
      )}

      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Stack direction="row" spacing={1} sx={{ mb: 2 }} useFlexGap flexWrap="wrap">
            <Chip label={question.cache_status || "未知"} color="primary" />
            <Chip label={question.provider_name || "-"} variant="outlined" />
            <Chip label={question.tool_id} variant="outlined" sx={{ fontFamily: "monospace" }} />
            <Chip label={`trace: ${question.trace_id}`} variant="outlined" sx={{ fontFamily: "monospace" }} />
          </Stack>
          <Typography variant="subtitle1" gutterBottom>
            结构化推演结果
          </Typography>
          {question.question_id === "q1" && q1Evidence ? (
            <Q1EvidencePanel
              evidence={q1Evidence as Q1PreprocessedEvidence}
              inference={q1Inference as WorkspaceDomainInferenceView}
              providerName={question.provider_name || traceDetail?.provider_name || null}
              elapsedMs={0} // No timing for production snapshot
            />
          ) : question.question_id === "q2" && q2Evidence ? (
            <Q2EvidencePanel
              evidence={q2Evidence as Q2PreprocessedEvidence}
              inference={q2Inference as Q2WhoAmIInferenceView}
              providerName={question.provider_name || traceDetail?.provider_name || null}
              elapsedMs={0} // No timing for production snapshot
            />
          ) : question.question_id === "q3" && q3Evidence ? (
            <Q3EvidencePanel
              evidence={q3Evidence as Q3PreprocessedEvidence}
              inference={q3Inference as Q3WhatDoIHaveInferenceView}
              providerName={question.provider_name || traceDetail?.provider_name || null}
              elapsedMs={0}
              trace={question.llm_trace_payload || traceDetail?.llm_trace_payload}
            />
          ) : question.question_id === "q4" && q4Evidence ? (
            <Q4EvidencePanel
              evidence={q4Evidence as Q4PreprocessedEvidence}
              inference={q4Inference as Q4WhatCanIDoInferenceView}
              providerName={question.provider_name || traceDetail?.provider_name || null}
              elapsedMs={0}
            />
          ) : question.question_id === "q5" && q5Evidence ? (
            <Q5EvidencePanel
              evidence={q5Evidence as Q5PreprocessedEvidence}
              inference={q5Inference as Q5WhatAmIAllowedToDoInferenceView}
              providerName={question.provider_name || traceDetail?.provider_name || null}
              elapsedMs={0}
            />
          ) : question.question_id === "q6" && q6Evidence ? (
            <Q6EvidencePanel
              evidence={q6Evidence as Q6PreprocessedEvidence}
              inference={q6Inference as Q6ForbiddenZoneInferenceView}
              providerName={question.provider_name || traceDetail?.provider_name || null}
              elapsedMs={0}
            />
          ) : question.question_id === "q7" && q7Evidence ? (
            <Q7EvidencePanel
              evidence={q7Evidence as Q7PreprocessedEvidence}
              inference={q7Inference as Q7AlternativeStrategyInferenceView}
              providerName={question.provider_name || traceDetail?.provider_name || null}
              elapsedMs={0}
            />
          ) : question.question_id === "q8" && q8Evidence ? (
            <Q8EvidencePanel
              evidence={q8Evidence as Q8PreprocessedEvidence}
              inference={q8Inference as Q8WhatShouldIDoNowInferenceView}
              providerName={question.provider_name || traceDetail?.provider_name || null}
              elapsedMs={0}
            />
          ) : question.question_id === "q9" && q9Evidence ? (
            <Q9EvidencePanel
              evidence={q9Evidence as Q9PreprocessedEvidence}
              inference={q9Inference as Q9ActionPostureInferenceView}
              providerName={question.provider_name || traceDetail?.provider_name || null}
              elapsedMs={0}
            />
          ) : (
            <Box
              component="pre"
              sx={{
                m: 0,
                p: 2,
                bgcolor: "action.hover",
                borderRadius: 1,
                overflow: "auto",
                fontSize: "0.85rem",
              }}
            >
              <code>{JSON.stringify(question.context_updates ?? question.result, null, 2)}</code>
            </Box>
          )}
        </CardContent>
      </Card>

      {question.question_id === "q1" || question.question_id === "q2" || question.question_id === "q8" || question.question_id === "q9" ? (
        <LLMTracePanel trace={llmTracePayload} />
      ) : (
      <Card variant="outlined">
        <CardContent>
          <Typography variant="h6" gutterBottom>
            调用链路溯源 (Trace Chain)
          </Typography>
          <Divider sx={{ mb: 2 }} />
          <Stack spacing={2}>
            <Accordion defaultExpanded>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography variant="subtitle2">{t("nineQuestions.promptOriginal")}</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Box
                  component="pre"
                  sx={{
                    m: 0,
                    p: 2,
                    bgcolor: "#1e1e1e",
                    color: "#cecece",
                    borderRadius: 1,
                    overflow: "auto",
                    whiteSpace: "pre-wrap",
                    fontSize: "0.85rem",
                  }}
                >
                  <code>{traceDetail?.prompt || "No prompt available"}</code>
                </Box>
              </AccordionDetails>
            </Accordion>

            <Accordion>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography variant="subtitle2">{t("nineQuestions.contextOriginal")}</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Box component="pre" sx={{ m: 0, p: 2, bgcolor: "action.hover", borderRadius: 1, overflow: "auto" }}>
                  <code>{JSON.stringify(traceDetail?.context || {}, null, 2)}</code>
                </Box>
              </AccordionDetails>
            </Accordion>

            <Accordion>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography variant="subtitle2">{t("nineQuestions.resultOriginal")}</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Box component="pre" sx={{ m: 0, p: 2, bgcolor: "action.hover", borderRadius: 1, overflow: "auto" }}>
                  <code>{JSON.stringify(traceDetail?.result || {}, null, 2)}</code>
                </Box>
              </AccordionDetails>
            </Accordion>
          </Stack>
        </CardContent>
      </Card>
      )}
    </Box>
  );
}
