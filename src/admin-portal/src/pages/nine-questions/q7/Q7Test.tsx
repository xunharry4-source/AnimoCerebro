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
  Q7PreprocessedEvidence,
  Q7AlternativeStrategyInferenceView,
  LLMTracePayloadView,
} from "../nineQuestionsApi";
import Q7EvidencePanel from "../../../components/Q7EvidencePanel";
import MountedPluginsZone from "../../../components/MountedPluginsZone";
import LLMTracePanel from "../../../components/LLMTracePanel";

export const Q7Test: React.FC = () => {
  const qId = "q7";
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
      // 物理接口绑定: GET /api/web/nine-questions/q7
      const question = await fetchNineQuestionDetail(qId);
      setDraftJson(JSON.stringify(question?.context_updates || {
        identity_kernel_constraints: ["dynamic goals cannot override non-bypassable constraints"],
        authorization_boundary_constraints: ["READ_ONLY_ACCESS", "requires_human_confirmation=true"],
        safety_rejection_history: ["G12 rejected force-write operation without confirmation"],
        procedural_memory_constraints: ["Do not bypass throttle or cloud audit for speed"],
        non_bypassable_constraints: ["DO_NOT_BYPASS_THROTTLE"],
      }, null, 2));
    } catch (err: any) {
      setErrorObj({ detail: err?.message || "加载 Q7 测试环境失败", error_code: "SANDBOX_SEED_ERROR" });
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
      <Typography variant="body2" color="text.secondary">正在初始化 Q7 沙箱环境...</Typography>
    </Box>
  );

  return (
    <Box sx={{ p: 2 }} data-testid="q7-test-root">
      <Typography variant="h4" fontWeight="bold" gutterBottom>
        {getQuestionDisplayLabel(qId)} 沙箱测试页
      </Typography>
      
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 5 }}>
          <Typography variant="h6" gutterBottom>构造故障场景 Mock 上下文 (JSON)</Typography>
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
            color="warning"
          >
            {running ? "执行红线评估..." : "发起红线约束推断"}
          </Button>

          {errorObj && (
            <Alert severity="error" sx={{ mt: 2 }}>
              <Typography variant="subtitle2" fontWeight="bold">沙箱熔断拦截 [{errorObj.error_code}]</Typography>
              <Typography variant="body2">{errorObj.detail || errorObj.message}</Typography>
            </Alert>
          )}
        </Grid>

        <Grid size={{ xs: 12, md: 7 }}>
          <Typography variant="h6" gutterBottom>沙箱红线评估结果 (Sandbox Results)</Typography>
          {!result && !errorObj && <Alert severity="info" variant="outlined">在此模拟安全拒绝、授权不足或程序记忆禁令下的红线推断。</Alert>}
          
          {result && (
            <Stack spacing={3}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="subtitle1" fontWeight="bold" gutterBottom>
                    【沙箱故障恢复算子挂载状态】
                  </Typography>
                  <MountedPluginsZone plugins={result.mounted_plugins || []} />
                  {(!result.mounted_plugins || result.mounted_plugins.length === 0) && (
                    <Alert severity="warning" sx={{ py: 0 }}>无激活的降级熔断算子保护</Alert>
                  )}
                </CardContent>
              </Card>

              {result.preprocessed_evidence && (
                <Q7EvidencePanel
                  evidence={result.preprocessed_evidence as Q7PreprocessedEvidence}
                  inference={result.inference_result as Q7AlternativeStrategyInferenceView}
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

export default Q7Test;
