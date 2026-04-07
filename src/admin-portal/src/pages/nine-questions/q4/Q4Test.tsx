import React, { useEffect, useState } from "react";
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
  fetchNineQuestionDetail,
  getQuestionDisplayLabel,
  LLMTracePayloadView,
  runNineQuestionSandboxTest,
  Q4PreprocessedEvidence,
  Q4WhatCanIDoInferenceView,
} from "../nineQuestionsApi";
import LLMTracePanel from "../../../components/LLMTracePanel";
import MountedPluginsZone from "../../../components/MountedPluginsZone";
import Q4EvidencePanel from "../../../components/Q4EvidencePanel";

export const Q4Test: React.FC = () => {
  const qId = "q4";
  const [mockJson, setMockJson] = useState("{}");
  const [result, setResult] = useState<any | null>(null);
  const [errorObj, setErrorObj] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    void loadSeed();
  }, []);

  const loadSeed = async () => {
    setLoading(true);
    try {
      const detail = await fetchNineQuestionDetail(qId);
      setMockJson(JSON.stringify(detail.context_updates || {}, null, 2));
      setErrorObj(null);
    } catch (err: any) {
      setErrorObj({ detail: err?.message || "加载 Q4 测试环境失败", error_code: "SANDBOX_SEED_ERROR" });
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async () => {
    setRunning(true);
    setErrorObj(null);
    setResult(null);
    try {
      const parsed = JSON.parse(mockJson || "{}");
      const data = await runNineQuestionSandboxTest("q4", parsed);
      setResult(data);
    } catch (err: any) {
      setErrorObj({ detail: err?.message || "执行 Q4 测试分析失败", error_code: "SANDBOX_CRASH" });
    } finally {
      setRunning(false);
    }
  };

  if (loading) return <CircularProgress />;

  return (
    <Box sx={{ p: 2 }} data-testid="q4-test-root">
      <Typography variant="h4" fontWeight="bold" gutterBottom>
        {getQuestionDisplayLabel(qId)} 沙箱测试页
      </Typography>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 4 }}>
          <Typography variant="h6" gutterBottom>构造极端 Mock 上下文 (JSON)</Typography>
          <TextField
            multiline
            fullWidth
            rows={20}
            value={mockJson}
            onChange={(e) => setMockJson(e.target.value)}
            sx={{ fontFamily: "monospace", mb: 2 }}
          />
          <Button variant="contained" disabled={running} onClick={handleTest} fullWidth>
            {running ? "执行防污染离线推理..." : "执行沙箱测试"}
          </Button>

          {errorObj && (
            <Alert severity="error" sx={{ mt: 2 }}>
              <Typography variant="subtitle2" fontWeight="bold">鉴权拦截或资源断连 [{errorObj.error_code}]</Typography>
              <Typography variant="body2">{errorObj.detail || errorObj.message}</Typography>
            </Alert>
          )}
        </Grid>

        <Grid size={{ xs: 12, md: 8 }}>
          <Typography variant="h6" gutterBottom>沙箱隔离输出结果 (Sandbox Results)</Typography>
          {!result && !errorObj && <Alert severity="info">尚未执行沙箱推断...</Alert>}

          {result && (
            <>
              <MountedPluginsZone plugins={result.mounted_plugins || []} />
              <Card variant="outlined" sx={{ mt: 2 }}>
                <CardContent>
                  <Q4EvidencePanel
                    evidence={result.preprocessed_evidence as Q4PreprocessedEvidence}
                    inference={result.inference_result as Q4WhatCanIDoInferenceView}
                    providerName={result.provider_name || null}
                    elapsedMs={result.elapsed_ms || 0}
                  />
                </CardContent>
              </Card>

              <LLMTracePanel trace={result.llm_trace_payload as LLMTracePayloadView} />
            </>
          )}
        </Grid>
      </Grid>
    </Box>
  );
};

export default Q4Test;
