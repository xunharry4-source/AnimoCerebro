import { useEffect, useState } from "react";
import { Alert, Box, Button, Card, CardContent, Chip, CircularProgress, Stack, Typography } from "@mui/material";
import { Link as RouterLink } from "react-router-dom";

import {
  fetchNineQuestionDetail,
  fetchNineQuestionTrace,
  getQuestionDisplayLabel,
  LLMTracePayloadView,
  NineQuestionItem,
  Q4PreprocessedEvidence,
  Q4WhatCanIDoInferenceView,
  TraceDetail,
} from "../nineQuestionsApi";
import LLMTracePanel from "../../../components/LLMTracePanel";
import NineQuestionIntroCard from "../../../components/NineQuestionIntroCard";
import MountedPluginsZone from "../../../components/MountedPluginsZone";
import Q4EvidencePanel from "../../../components/Q4EvidencePanel";

export default function Q4Detail() {
  const qId = "q4";
  const [question, setQuestion] = useState<NineQuestionItem | null>(null);
  const [traceDetail, setTraceDetail] = useState<TraceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    void loadDetail();
  }, []);

  const loadDetail = async () => {
    setLoading(true);
    try {
      const detail = await fetchNineQuestionDetail(qId);
      setQuestion(detail);
      if (detail.trace_id) {
        const trace = await fetchNineQuestionTrace(detail.trace_id);
        setTraceDetail(trace);
      }
      setErrorMsg("");
    } catch (err: any) {
      setErrorMsg(err?.message || "加载 Q4 详情失败");
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <CircularProgress />;
  if (errorMsg) return <Alert severity="error">{errorMsg}</Alert>;
  if (!question) return <Alert severity="warning">未能找到 Q4 报告记录</Alert>;

  const evidence = (question.preprocessed_evidence || traceDetail?.preprocessed_evidence) as Q4PreprocessedEvidence;
  const inference = (question.inference_result || traceDetail?.inference_result) as Q4WhatCanIDoInferenceView;
  const llmTrace = question.llm_trace_payload || traceDetail?.llm_trace_payload;

  return (
    <Box data-testid="q4-detail-root">
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Box>
          <Typography variant="h4" gutterBottom>{getQuestionDisplayLabel(qId)} 正式审计页</Typography>
          <Typography variant="body2" color="text.secondary">Capability Boundary & Actionable Space Audit</Typography>
        </Box>
        <Button component={RouterLink} to="/console/nine-questions/q4/test" variant="contained" color="warning">进入独立沙箱测试</Button>
      </Stack>

      <NineQuestionIntroCard questionId="q4" />

      <MountedPluginsZone plugins={question.mounted_plugins || []} />

      <Card variant="outlined" sx={{ mb: 3, mt: 2 }}>
        <CardContent>
          <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
            <Chip label={question.cache_status} color="primary" />
            <Chip label={question.provider_name} variant="outlined" />
            <Chip label={question.tool_id} variant="outlined" sx={{ fontFamily: "monospace" }} />
          </Stack>

          <Typography variant="h6" gutterBottom sx={{ mt: 2, fontWeight: "bold" }}>
            结构化能力边界证据 (Zentex G31A.Q4)
          </Typography>

          {evidence ? (
            <Q4EvidencePanel
              evidence={evidence}
              inference={inference}
              providerName={question.provider_name || traceDetail?.provider_name || null}
              elapsedMs={llmTrace?.elapsed_ms || 0}
            />
          ) : (
            <Alert severity="warning">暂无结构化能力证据。</Alert>
          )}
        </CardContent>
      </Card>

      <LLMTracePanel trace={llmTrace as LLMTracePayloadView} />
    </Box>
  );
}
