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
  CircularProgress,
  Grid,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { useParams } from "react-router-dom";

import {
  NineQuestionSandboxResponse,
  fetchNineQuestionDetail,
  getQuestionDisplayLabel,
  runNineQuestionSandboxTest,
  Q2PreprocessedEvidence,
  Q2WhoAmIInferenceView,
  LLMTracePayloadView,
} from "../nineQuestionsApi";
import Q2EvidencePanel from "../../../components/Q2EvidencePanel";
import MountedPluginsZone from "../../../components/MountedPluginsZone";
import LLMTracePanel from "../../../components/LLMTracePanel";

export default function Q2Test() {
  const qId = "q2";
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
      const question = await fetchNineQuestionDetail(qId);
      setDraftJson(JSON.stringify(question?.context_updates || {}, null, 2));
    } catch (err: any) {
      setError(err?.message || "加载 Q2 测试环境失败");
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
      setError(err?.message || "执行 Q2 测试分析失败");
    } finally {
      setRunning(false);
    }
  };

  if (loading) return <CircularProgress />;

  return (
    <Box>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" gutterBottom>{getQuestionDisplayLabel(qId)} 沙箱测试页</Typography>
        <Typography variant="body2" color="text.secondary">用于在隔离环境下注入 Mock 上下文并触发身份核心审计 (Anti-Contamination)</Typography>
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
              <Button variant="contained" sx={{ mt: 2 }} onClick={() => void handleRun()} disabled={running}>执行测试分析</Button>
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
                      <Q2EvidencePanel
                        evidence={result.preprocessed_evidence as Q2PreprocessedEvidence}
                        inference={result.inference_result as Q2WhoAmIInferenceView}
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
