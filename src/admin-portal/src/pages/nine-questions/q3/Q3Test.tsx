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
  Q3PreprocessedEvidence,
  Q3WhatDoIHaveInferenceView,
} from "../nineQuestionsApi";
import Q3EvidencePanel from "../../../components/Q3EvidencePanel";
import MountedPluginsZone from "../../../components/MountedPluginsZone";

export default function Q3Test() {
  const qId = "q3";
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
    try {
      const detail = await fetchNineQuestionDetail(qId);
      setDraftJson(JSON.stringify(detail.context_updates || {}, null, 2));
    } catch (err: any) {
      setError(err?.message || "加载 Q3 测试环境失败");
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
      setError(err?.message || "执行 Q3 测试分析失败");
    } finally {
      setRunning(false);
    }
  };

  if (loading) return <CircularProgress />;

  return (
    <Box data-testid="q3-test-root">
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" gutterBottom>{getQuestionDisplayLabel(qId)} 沙箱测试页</Typography>
        <Typography variant="body2" color="text.secondary">用于在隔离环境下注入 Mock 上下文并触发资源盘点审计 (Anti-Contamination)</Typography>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

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
              />
              <Button variant="contained" sx={{ mt: 2 }} onClick={() => void handleRun()} disabled={running}>执行沙箱测试</Button>
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
                      <Q3EvidencePanel
                        evidence={result.preprocessed_evidence as Q3PreprocessedEvidence}
                        inference={result.inference_result as Q3WhatDoIHaveInferenceView}
                        providerName={result.provider_name || null}
                        elapsedMs={result.elapsed_ms || 0}
                        trace={result.llm_trace_payload}
                      />
                    </Box>
                  )}
                </>
              ) : <Typography color="text.secondary">等待执行结果...</Typography>}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
