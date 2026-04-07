import { useEffect, useState } from "react";
import { Alert, Box, Button, Card, CardContent, CircularProgress, Divider, Grid, List, ListItem, ListItemText, Stack, TextField, Typography } from "@mui/material";
import { useParams } from "react-router-dom";

import {
  NineQuestionSandboxResponse,
  ReportPayload,
  fetchNineQuestionsReport,
  getQuestionDisplayLabel,
  runNineQuestionSandboxTest,
} from "./nineQuestionsApi";
import Q1EvidencePanel from "../../components/Q1EvidencePanel";
import Q2EvidencePanel from "../../components/Q2EvidencePanel";
import Q3EvidencePanel from "../../components/Q3EvidencePanel";
import Q4EvidencePanel from "../../components/Q4EvidencePanel";
import Q5EvidencePanel from "../../components/Q5EvidencePanel";
import { Q6EvidencePanel } from "../../components/Q6EvidencePanel";
import { Q7EvidencePanel } from "../../components/Q7EvidencePanel";
import Q8EvidencePanel from "../../components/Q8EvidencePanel";
import Q9EvidencePanel from "../../components/Q9EvidencePanel";
import LLMTracePanel from "../../components/LLMTracePanel";
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

function renderJsonBlock(value: unknown, minHeight = 120) {
  return (
    <Box
      component="pre"
      sx={{
        m: 0,
        p: 2,
        minHeight,
        bgcolor: "action.hover",
        borderRadius: 1,
        overflow: "auto",
        fontSize: "0.85rem",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
      }}
    >
      <code>{JSON.stringify(value, null, 2)}</code>
    </Box>
  );
}

export default function NineQuestionSandboxPage() {
  const { q_id: qId = "" } = useParams();
  const [report, setReport] = useState<ReportPayload | null>(null);
  const [draftJson, setDraftJson] = useState("{}");
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<NineQuestionSandboxResponse | null>(null);

  useEffect(() => {
    void loadQuestion();
  }, [qId]);

  const loadQuestion = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchNineQuestionsReport();
      setReport(data.report);
      const question = data.report.questions.find((item) => item.question_id === qId);
      setDraftJson(JSON.stringify(question?.context_updates || {}, null, 2));
    } catch (err: any) {
      setError(err?.message || "加载九问沙箱失败");
    } finally {
      setLoading(false);
    }
  };

  const question = report?.questions.find((item) => item.question_id === qId);

  const handleFillLiveContext = () => {
    setDraftJson(JSON.stringify(question?.context_updates || {}, null, 2));
  };

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    try {
      const mockContext = JSON.parse(draftJson || "{}");
      const sandboxResult = await runNineQuestionSandboxTest(qId, mockContext);
      setResult(sandboxResult);
    } catch (err: any) {
      setError(err?.message || "执行九问沙箱失败");
    } finally {
      setRunning(false);
    }
  };

  if (loading) {
    return <CircularProgress />;
  }

  return (
    <Box>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" gutterBottom>
          {getQuestionDisplayLabel(qId)} 沙箱测试
        </Typography>
        <Typography variant="body2" color="text.secondary">
          左侧注入 Mock Context，右侧查看隔离沙箱提取到的本地预处理证据与最终推断。该页面只调用沙箱接口，不会覆盖主脑缓存或写入正式事件流。
        </Typography>
      </Box>

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      ) : null}

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 5 }}>
          <Card variant="outlined" sx={{ height: "100%" }}>
            <CardContent>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
                <Typography variant="h6">上下文注入区</Typography>
                <Button variant="text" onClick={handleFillLiveContext}>
                  一键填充当前主脑上下文
                </Button>
              </Stack>
              <TextField
                fullWidth
                multiline
                minRows={18}
                label="Mock 上下文 JSON"
                value={draftJson}
                onChange={(event) => setDraftJson(event.target.value)}
              />
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 7 }}>
          <Card variant="outlined" sx={{ height: "100%" }}>
            <CardContent>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
                <Typography variant="h6">执行与结果区</Typography>
                <Button variant="contained" onClick={() => void handleRun()} disabled={running}>
                  执行测试
                </Button>
              </Stack>
              {running ? <CircularProgress /> : null}
              {question ? (
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  当前目标: {question.title} | Provider: {question.provider_name || "-"}
                </Typography>
              ) : null}
              {result ? (
                <>
                  <Alert severity="success" sx={{ mb: 2 }}>
                    {result.summary}
                  </Alert>
                  {qId === "q1" && result.preprocessed_evidence ? (
                    <Q1EvidencePanel
                      evidence={result.preprocessed_evidence as Q1PreprocessedEvidence}
                      inference={result.inference_result as WorkspaceDomainInferenceView}
                      providerName={result.provider_name || null}
                      elapsedMs={result.elapsed_ms || 0}
                    />
                  ) : qId === "q2" && result.preprocessed_evidence ? (
                    <Q2EvidencePanel
                      evidence={result.preprocessed_evidence as Q2PreprocessedEvidence}
                      inference={result.inference_result as Q2WhoAmIInferenceView}
                      providerName={result.provider_name || null}
                      elapsedMs={result.elapsed_ms || 0}
                    />
                  ) : qId === "q3" && result.preprocessed_evidence ? (
                    <Q3EvidencePanel
                      evidence={result.preprocessed_evidence as Q3PreprocessedEvidence}
                      inference={result.inference_result as Q3WhatDoIHaveInferenceView}
                      providerName={result.provider_name || null}
                      elapsedMs={result.elapsed_ms || 0}
                      trace={result.llm_trace_payload}
                    />
                  ) : qId === "q4" && result.preprocessed_evidence ? (
                    <Q4EvidencePanel
                      evidence={result.preprocessed_evidence as Q4PreprocessedEvidence}
                      inference={result.inference_result as Q4WhatCanIDoInferenceView}
                      providerName={result.provider_name || null}
                      elapsedMs={result.elapsed_ms || 0}
                    />
                  ) : qId === "q5" && result.preprocessed_evidence ? (
                    <Q5EvidencePanel
                      evidence={result.preprocessed_evidence as Q5PreprocessedEvidence}
                      inference={result.inference_result as Q5WhatAmIAllowedToDoInferenceView}
                      providerName={result.provider_name || null}
                      elapsedMs={result.elapsed_ms || 0}
                    />
                  ) : qId === "q6" && result.preprocessed_evidence ? (
                    <Q6EvidencePanel
                      evidence={result.preprocessed_evidence as Q6PreprocessedEvidence}
                      inference={result.inference_result as Q6ForbiddenZoneInferenceView}
                      providerName={result.provider_name || null}
                      elapsedMs={result.elapsed_ms || 0}
                    />
                  ) : qId === "q7" && result.preprocessed_evidence ? (
                    <Q7EvidencePanel
                      evidence={result.preprocessed_evidence as Q7PreprocessedEvidence}
                      inference={result.inference_result as Q7AlternativeStrategyInferenceView}
                      providerName={result.provider_name || null}
                      elapsedMs={result.elapsed_ms || 0}
                    />
                  ) : qId === "q8" && result.preprocessed_evidence ? (
                    <Q8EvidencePanel
                      evidence={result.preprocessed_evidence as Q8PreprocessedEvidence}
                      inference={result.inference_result as Q8WhatShouldIDoNowInferenceView}
                      providerName={result.provider_name || null}
                      elapsedMs={result.elapsed_ms || 0}
                    />
                  ) : qId === "q9" && result.preprocessed_evidence ? (
                    <Q9EvidencePanel
                      evidence={result.preprocessed_evidence as Q9PreprocessedEvidence}
                      inference={result.inference_result as Q9ActionPostureInferenceView}
                      providerName={result.provider_name || null}
                      elapsedMs={result.elapsed_ms || 0}
                    />
                  ) : (
                    renderJsonBlock(
                      {
                        elapsed_ms: result.elapsed_ms,
                        provider_name: result.provider_name,
                        summary: result.summary,
                        result: result.result,
                        context_updates: result.context_updates,
                      },
                      320,
                    )
                  )}
                  {qId === "q1" || qId === "q2" || qId === "q6" || qId === "q7" || qId === "q8" || qId === "q9" ? (
                    <LLMTracePanel trace={result.llm_trace_payload} />
                  ) : null}
                </>
              ) : (
                renderJsonBlock("等待执行结果...", 320)
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
