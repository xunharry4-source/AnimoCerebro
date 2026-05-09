import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Grid,
  TextField,
  Typography,
} from "@mui/material";
import {
  NineQuestionSandboxResponse,
  fetchNineQuestionDetail,
  getQuestionDisplayLabel,
  runNineQuestionSandboxTest,
  Q5PreprocessedEvidence,
  Q5WhatAmIAllowedToDoInferenceView,
  LLMTracePayloadView,
} from "../nineQuestionsApi";
import Q5EvidencePanel from "../../../components/Q5EvidencePanel";
import MountedPluginsZone from "../../../components/MountedPluginsZone";
import LLMTracePanel from "../../../components/LLMTracePanel";

export default function Q5Test() {
  const qId = "q5";
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
      // 物理接口绑定: GET /api/web/nine-questions/q5
      const question = await fetchNineQuestionDetail(qId);
      setDraftJson(JSON.stringify(question?.context_updates || {}, null, 2));
    } catch (err: any) {
      setError(err?.message || "加载 Q5 测试环境失败");
    } finally {
      setLoading(false);
    }
  };

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    try {
      const mockContext = JSON.parse(draftJson || "{}");
      // 沙箱隔离调用
      const sandboxResult = await runNineQuestionSandboxTest(qId, mockContext);
      setResult(sandboxResult);
    } catch (err: any) {
      setError(err?.message || "执行 Q5 测试分析失败");
    } finally {
      setRunning(false);
    }
  };

  if (loading) return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 2, p: 3 }}>
      <CircularProgress size={24} />
      <Typography variant="body2" color="text.secondary">正在初始化 Q5 沙箱环境...</Typography>
    </Box>
  );

  return (
    <Box data-testid="q5-test-root">
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" gutterBottom>{getQuestionDisplayLabel(qId)} 沙箱测试页</Typography>
        <Typography variant="body2" color="text.secondary">用于在隔离环境下注入 Mock 上下文并触发权限合规审计 (Anti-Contamination)</Typography>
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
                      <Q5EvidencePanel
                        evidence={result.preprocessed_evidence as Q5PreprocessedEvidence}
                        inference={result.inference_result as Q5WhatAmIAllowedToDoInferenceView}
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
