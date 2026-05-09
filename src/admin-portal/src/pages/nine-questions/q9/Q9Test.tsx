import { useEffect, useState } from "react";
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
  Q9PreprocessedEvidence,
  Q9ActionPostureInferenceView,
  LLMTracePayloadView,
} from "../nineQuestionsApi";
import Q9EvidencePanel from "../../../components/Q9EvidencePanel";
import MountedPluginsZone from "../../../components/MountedPluginsZone";
import LLMTracePanel from "../../../components/LLMTracePanel";

export default function Q9Test() {
  const qId = "q9";
  const [draftJson, setDraftJson] = useState("{}");
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<NineQuestionSandboxResponse | null>(null);

  useEffect(() => {
    void loadQuestion();
  }, []);

  const loadQuestion = async () => {
    setLoading(true);
    setError(null);
    try {
      // 物理接口绑定: GET /api/web/nine-questions/q9
      const question = await fetchNineQuestionDetail(qId);
      setDraftJson(JSON.stringify(question?.context_updates || {
        cognitive_snapshot: {
          uncertainty_count: 2,
          absolute_red_line_count: 0,
          q1_to_q8_snapshot: { status: "nominal" }
        },
        self_model: {
          cognitive_load: "low",
          stability_level: "high",
          confidence_drift: 0.05,
          recent_weaknesses: []
        },
        reasoning_budget: {
          compute_remaining_ratio: 0.85,
          token_remaining_ratio: 0.9,
          time_remaining_ratio: 0.95,
          budget_pressure: "low"
        }
      }, null, 2));
    } catch (err: any) {
      setError({ detail: err?.message || "加载 Q9 测试环境失败", error_code: "SANDBOX_SEED_ERROR" } as any);
    } finally {
      setLoading(false);
    }
  };

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    try {
      const mockContext = JSON.parse(draftJson || "{}");
      const sandboxResult = await runNineQuestionSandboxTest(qId, mockContext);
      setResult(sandboxResult);
    } catch (err: any) {
      setError(err?.message || "执行 Q9 测试分析失败");
    } finally {
      setRunning(false);
    }
  };

  if (loading) return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 2, p: 3 }}>
      <CircularProgress size={24} />
      <Typography variant="body2" color="text.secondary">正在初始化 Q9 沙箱环境...</Typography>
    </Box>
  );

  return (
    <Box data-testid="q9-test-root">
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" gutterBottom>{getQuestionDisplayLabel(qId)} 沙箱测试页</Typography>
        <Typography variant="body2" color="text.secondary">用于在隔离环境下注入 Mock 上下文并触发自愈行动策略审计 (Anti-Contamination)</Typography>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{String(error)}</Alert>}

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 5 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>Mock Context Injection</Typography>
              <TextField
                fullWidth
                multiline
                minRows={18}
                value={draftJson}
                onChange={(e) => setDraftJson(e.target.value)}
                sx={{ fontFamily: "monospace" }}
              />
              <Button
                variant="contained"
                sx={{ mt: 2 }}
                onClick={() => void handleRun()}
                disabled={running}
              >
                执行沙箱测试
              </Button>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 7 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>推演执行结果 (Sandbox Result)</Typography>
              {running && <CircularProgress size={24} />}
              {result ? (
                <>
                  <Alert severity="success" sx={{ mb: 2 }}>{result.summary}</Alert>
                  <MountedPluginsZone plugins={result.mounted_plugins || []} />
                  {result.preprocessed_evidence && (
                    <Box sx={{ mt: 2 }}>
                      <Q9EvidencePanel
                        evidence={result.preprocessed_evidence as Q9PreprocessedEvidence}
                        inference={result.inference_result as Q9ActionPostureInferenceView}
                        providerName={result.provider_name || null}
                        elapsedMs={result.elapsed_ms || 0}
                      />
                    </Box>
                  )}
                  <Box sx={{ mt: 3 }}>
                    <LLMTracePanel trace={result.llm_trace_payload as LLMTracePayloadView} />
                  </Box>
                </>
              ) : <Typography color="text.secondary">等待执行结果...</Typography>}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
