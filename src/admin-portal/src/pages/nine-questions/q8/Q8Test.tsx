import React, { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Grid,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import {
  NineQuestionSandboxResponse,
  fetchNineQuestionDetail,
  getQuestionDisplayLabel,
  runNineQuestionSandboxTest,
  Q8PreprocessedEvidence,
  Q8WhatShouldIDoNowInferenceView,
  LLMTracePayloadView,
} from "../nineQuestionsApi";
import Q8EvidencePanel from "../../../components/Q8EvidencePanel";
import LLMTracePanel from "../../../components/LLMTracePanel";

export const Q8Test: React.FC = () => {
  const qId = "q8";
  const [draftJson, setDraftJson] = useState("{}");
  const [result, setResult] = useState<NineQuestionSandboxResponse | null>(null);
  const [errorObj, setErrorObj] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    void loadQuestion();
  }, []);

  const loadQuestion = async () => {
    setLoading(true);
    setErrorObj(null);
    try {
      // 物理接口绑定: GET /api/web/nine-questions/q8
      const question = await fetchNineQuestionDetail(qId);
      setDraftJson(JSON.stringify(question?.context_updates || {
        aggregated_context: {
          absolute_red_line_count: 5,
          capability_ceiling_count: 12,
          q1_to_q7_snapshot: { warning: "FAKE_MASSIVE_CONTEXT_PAYLOAD_HERE_OVERRIDE_AT_WILL" }
        },
        runtime_state: {
          persistent_task_state: [
            { item_id: "T-01", title: "Wait for deployment auth", status: "blocked", blocker_reason: "Awaiting DBA signoff" }
          ],
          cognitive_agenda: [
            { item_id: "C-01", title: "Investigate elevated latency on database", status: "overdue", delay_risk_score: 95, next_review_condition: "When CPU > 80%" }
          ]
        }
      }, null, 2));
    } catch (err: any) {
      setErrorObj({ detail: err?.message || "加载 Q8 测试环境失败", error_code: "SANDBOX_SEED_ERROR" });
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async () => {
    setRunning(true);
    setErrorObj(null);
    setResult(null);
    try {
      const parsed = JSON.parse(draftJson || "{}");
      // 沙箱隔离调用
      const data = await runNineQuestionSandboxTest(qId, parsed);
      setResult(data);
    } catch (err: any) {
      if (err.data && err.data.error_code) {
        setErrorObj(err.data);
      } else {
        setErrorObj({ detail: err.message, error_code: "SANDBOX_CRASH" });
      }
    } finally {
      setRunning(false);
    }
  };

  if (loading) return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 2, p: 3 }}>
      <CircularProgress size={24} />
      <Typography variant="body2" color="text.secondary">正在初始化 Q8 沙箱环境...</Typography>
    </Box>
  );

  return (
    <Box sx={{ p: 2 }} data-testid="q8-test-root">
      <Typography variant="h4" fontWeight="bold" gutterBottom>
        {getQuestionDisplayLabel(qId)} 沙箱测试页
      </Typography>
      
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 5 }}>
          <Typography variant="h6" gutterBottom>构造终局决策 Mock 上下文 (JSON)</Typography>
          <TextField
            multiline
            fullWidth
            minRows={25}
            value={draftJson}
            onChange={(e) => setDraftJson(e.target.value)}
            sx={{ fontFamily: "monospace", mb: 2 }}
          />
          <Button
            variant="contained"
            disabled={running}
            onClick={() => void handleTest()}
            fullWidth
            color="primary"
          >
            {running ? "引爆核心主张引擎计算..." : "投喂越界快照发起沙箱定调"}
          </Button>

          {errorObj && (
            <Alert severity="error" sx={{ mt: 2 }}>
              <Typography variant="subtitle2" fontWeight="bold">沙箱定调崩溃 [{errorObj.error_code}]</Typography>
              <Typography variant="body2">{errorObj.detail || errorObj.message}</Typography>
            </Alert>
          )}
        </Grid>

        <Grid size={{ xs: 12, md: 7 }}>
          <Typography variant="h6" gutterBottom>核心主脑推演隔离结果 (Sandbox Results)</Typography>
          {!result && !errorObj && <Alert severity="info" variant="outlined">在绝对防污染环境中安全预演大模型的暴走可能...</Alert>}
          
          {result && (
            <Stack spacing={3}>
              {result.preprocessed_evidence && (
                <Q8EvidencePanel
                  evidence={result.preprocessed_evidence as Q8PreprocessedEvidence}
                  inference={result.inference_result as Q8WhatShouldIDoNowInferenceView}
                  providerName={result.provider_name || null}
                  elapsedMs={result.elapsed_ms || 0}
                />
              )}

              <LLMTracePanel trace={result.llm_trace_payload as LLMTracePayloadView} />
            </Stack>
          )}
        </Grid>
      </Grid>
    </Box>
  );
};

export default Q8Test;
