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
  Q6PreprocessedEvidence,
  LLMTracePayloadView,
} from "../nineQuestionsApi";
import Q6EvidencePanel from "../../../components/Q6EvidencePanel";
import MountedPluginsZone from "../../../components/MountedPluginsZone";
import LLMTracePanel from "../../../components/LLMTracePanel";

export const Q6Test: React.FC = () => {
  const qId = "q6";
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
      // 物理接口绑定: GET /api/web/nine-questions/q6
      const question = await fetchNineQuestionDetail(qId);
      setDraftJson(JSON.stringify(question?.context_updates || {
        actionable_space: ["CRITICAL_WRITE", "DEPLOY_TO_PROD"],
        authorization_boundaries: ["DEV_ONLY"],
        non_bypassable_constraints: ["MUST_HAVE_HUMAN_APPROVAL_FOR_PROD"],
        historical_strategy_patches: [
          "2025-01-01: Auto-deploy to prod failed catastrophically. Added strict requirement to never deploy without manual ticket linked."
        ]
      }, null, 2));
    } catch (err: any) {
      setErrorObj({ detail: err?.message || "加载 Q6 测试环境失败", error_code: "SANDBOX_SEED_ERROR" });
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
      <Typography variant="body2" color="text.secondary">正在初始化 Q6 沙箱环境...</Typography>
    </Box>
  );

  return (
    <Box sx={{ p: 2 }} data-testid="q6-test-root">
      <Typography variant="h4" fontWeight="bold" gutterBottom>
        {getQuestionDisplayLabel(qId)} 沙箱测试页
      </Typography>
      
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 5 }}>
          <Typography variant="h6" gutterBottom>构造极端 Mock 上下文 (JSON)</Typography>
          <TextField
            multiline
            fullWidth
            minRows={20}
            value={draftJson}
            onChange={(e) => setDraftJson(e.target.value)}
            sx={{ fontFamily: "monospace", mb: 2 }}
          />
          <Button
            variant="contained"
            disabled={running}
            onClick={() => void handleTest()}
            fullWidth
            color="error"
          >
            {running ? "执行阻断推演..." : "发起高危越权探测"}
          </Button>

          {errorObj && (
            <Alert severity="error" sx={{ mt: 2 }}>
              <Typography variant="subtitle2" fontWeight="bold">沙箱被动触发拦截 [{errorObj.error_code}]</Typography>
              <Typography variant="body2">{errorObj.detail || errorObj.message}</Typography>
            </Alert>
          )}
        </Grid>

        <Grid size={{ xs: 12, md: 7 }}>
          <Typography variant="h6" gutterBottom>沙箱隔离输出结果 (Sandbox Results)</Typography>
          {!result && !errorObj && <Alert severity="info" variant="outlined">等待触发阻断演练...</Alert>}
          
          {result && (
            <Stack spacing={3}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="subtitle1" fontWeight="bold" gutterBottom>
                    【高危侦测算子池 (Sandbox Redline Evaluators)】
                  </Typography>
                  <MountedPluginsZone plugins={result.mounted_plugins || []} />
                  {(!result.mounted_plugins || result.mounted_plugins.length === 0) && (
                    <Alert severity="warning">未挂载任何防御算子，属于极度裸奔状态</Alert>
                  )}
                </CardContent>
              </Card>

              {result.preprocessed_evidence && (
                <Q6EvidencePanel
                  evidence={result.preprocessed_evidence as Q6PreprocessedEvidence}
                  inference={result.inference_result as any}
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

export default Q6Test;
