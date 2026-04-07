import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { type ModelFeatureCatalogItem } from "./TestPage";
import { fetchLlmStatus, type LLMStatus } from "../../api/llmStatus";

type InvokeResponse = {
  feature_id: string;
  feature_name: string;
  test_run_id: string;
  started_at: string;
  finished_at: string;
  status: string;
  effective_context: Record<string, unknown>;
  result: unknown;
  trace_id: string | null;
  request_id: string | null;
  request_count: number;
  token_stats: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
  aggregate_request_count: number;
  aggregate_token_stats: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
  llm_calls: Array<Record<string, unknown>>;
  replay: Record<string, unknown> | null;
  recent_events: Array<Record<string, unknown>>;
  audit_log_path: string | null;
};

type ModelFeatureTestPageProps = {
  featureId: string;
  onBack: () => void;
};

type RunLogResponse = {
  item: Record<string, unknown>;
  log: Record<string, unknown>;
  replay: Record<string, unknown> | null;
  recent_events: Array<Record<string, unknown>>;
};

type StatsResponse = {
  request_count: number;
  token_stats: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
  by_feature: Record<string, { request_count: number; input_tokens: number; output_tokens: number; total_tokens: number }>;
};

function toPrettyJson(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}

export default function ModelFeatureTestPage({ featureId, onBack }: ModelFeatureTestPageProps) {
  const [catalog, setCatalog] = useState<ModelFeatureCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [invoking, setInvoking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [invokeError, setInvokeError] = useState<string | null>(null);
  const [llmStatus, setLlmStatus] = useState<LLMStatus | null>(null);
  const [baseContextText, setBaseContextText] = useState("{}");
  const [injectionText, setInjectionText] = useState("{}");
  const [invokeResult, setInvokeResult] = useState<InvokeResponse | null>(null);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [defaultBaseContextText, setDefaultBaseContextText] = useState("{}");
  const [defaultInjectionText, setDefaultInjectionText] = useState("{}");
  const [currentLogLoading, setCurrentLogLoading] = useState(false);
  const [currentLogError, setCurrentLogError] = useState<string | null>(null);
  const [currentRunLog, setCurrentRunLog] = useState<RunLogResponse | null>(null);

  useEffect(() => {
    const loadCatalog = async () => {
      setLoading(true);
      try {
        try {
          setLlmStatus(await fetchLlmStatus(true));
        } catch {
          setLlmStatus({ available: false, reason: "status_check_failed", hint: "LLM 状态检查失败" });
        }

        const response = await fetch("/api/web/tests/model-features", {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error("catalog_failed");
        }
        const data = (await response.json()) as ModelFeatureCatalogItem[];
        setCatalog(data);
        setError(null);
      } catch {
        setError("无法加载测试功能定义，请检查后端状态。");
      } finally {
        setLoading(false);
      }
    };
    void loadCatalog();
  }, []);

  useEffect(() => {
    const loadStats = async () => {
      try {
        const response = await fetch(
          `/api/web/tests/model-features/stats?feature_id=${encodeURIComponent(featureId)}`,
          { headers: { Accept: "application/json" } },
        );
        if (!response.ok) {
          return;
        }
        setStats((await response.json()) as StatsResponse);
      } catch {
        setStats(null);
      }
    };
    void loadStats();
  }, [featureId]);

  const feature = useMemo(
    () => catalog.find((item) => item.feature_id === featureId) ?? null,
    [catalog, featureId],
  );

  useEffect(() => {
    if (!feature) {
      return;
    }
    const baseSample = toPrettyJson(feature.default_payload?.base_context ?? {});
    const injectionSample = toPrettyJson(feature.default_payload?.injection ?? {});
    setDefaultBaseContextText(baseSample);
    setDefaultInjectionText(injectionSample);
    setBaseContextText(baseSample);
    setInjectionText(injectionSample);
  }, [feature]);

  const invokeFeature = async () => {
    if (llmStatus && llmStatus.available === false) {
      setInvokeError(`LLM 不可用，已禁止调用。${llmStatus.hint ? ` (${llmStatus.hint})` : ""}`);
      return;
    }
    let parsedBaseContext: Record<string, unknown>;
    let parsedInjection: Record<string, unknown>;
    try {
      parsedBaseContext = JSON.parse(baseContextText) as Record<string, unknown>;
      parsedInjection = JSON.parse(injectionText) as Record<string, unknown>;
    } catch {
      setInvokeError("JSON 解析失败，请检查 base_context / injection 格式。");
      return;
    }

    setInvoking(true);
    setCurrentRunLog(null);
    setCurrentLogError(null);
    try {
      const response = await fetch(`/api/web/tests/model-features/${encodeURIComponent(featureId)}/invoke`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          base_context: parsedBaseContext,
          injection: parsedInjection,
        }),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      setInvokeResult((await response.json()) as InvokeResponse);
      setInvokeError(null);
      try {
        const statsResponse = await fetch(
          `/api/web/tests/model-features/stats?feature_id=${encodeURIComponent(featureId)}`,
          { headers: { Accept: "application/json" } },
        );
        if (statsResponse.ok) {
          setStats((await statsResponse.json()) as StatsResponse);
        }
      } catch {
        setStats(null);
      }
    } catch (err) {
      setInvokeResult(null);
      setInvokeError(
        err instanceof Error ? `调用失败: ${err.message}` : "调用失败，请检查后端日志。",
      );
    } finally {
      setInvoking(false);
    }
  };

  const loadCurrentRunLog = async () => {
    if (llmStatus && llmStatus.available === false) {
      setCurrentLogError("LLM 不可用，已禁止加载日志。");
      return;
    }
    if (!invokeResult?.test_run_id) {
      return;
    }
    setCurrentLogLoading(true);
    try {
      const response = await fetch(
        `/api/web/tests/model-features/runs/${encodeURIComponent(invokeResult.test_run_id)}`,
        { headers: { Accept: "application/json" } },
      );
      if (!response.ok) {
        throw new Error("current_run_log_failed");
      }
      setCurrentRunLog((await response.json()) as RunLogResponse);
      setCurrentLogError(null);
    } catch {
      setCurrentRunLog(null);
      setCurrentLogError("无法加载当前测试的详细日志。");
    } finally {
      setCurrentLogLoading(false);
    }
  };

  if (loading) {
    return (
      <Stack spacing={2}>
        <Typography variant="h4" component="h1">模型功能测试</Typography>
        <Stack direction="row" spacing={1} alignItems="center">
          <CircularProgress size={18} />
          <Typography variant="body2">加载中...</Typography>
        </Stack>
      </Stack>
    );
  }

  if (error) {
    return (
      <Stack spacing={2}>
        <Typography variant="h4" component="h1">模型功能测试</Typography>
        <Alert severity="error">{error}</Alert>
        <Button variant="outlined" onClick={onBack}>返回测试列表</Button>
      </Stack>
    );
  }

  if (!feature) {
    return (
      <Stack spacing={2}>
        <Typography variant="h4" component="h1">模型功能测试</Typography>
        <Alert severity="warning">未找到功能定义：{featureId}</Alert>
        <Button variant="outlined" onClick={onBack}>返回测试列表</Button>
      </Stack>
    );
  }

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Box>
          <Typography variant="h4" component="h1">{feature.feature_name}</Typography>
          <Typography variant="body2" color="text.secondary">{feature.description}</Typography>
        </Box>
        <Button variant="outlined" onClick={onBack}>返回测试列表</Button>
      </Stack>

      {llmStatus && llmStatus.available === false ? (
        <Alert severity="error">
          LLM 不可用，已禁止所有测试功能操作。{llmStatus.hint ? ` (${llmStatus.hint})` : ""}
        </Alert>
      ) : null}

      {invokeError ? <Alert severity="error">{invokeError}</Alert> : null}

      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="h6">手动注入参数</Typography>
            <Alert severity="info">
              <Typography variant="body2">
                <strong>base_context</strong>：该功能的基础输入上下文（默认样例可直接改）。
              </Typography>
              <Typography variant="body2">
                <strong>injection</strong>：覆盖/补丁参数，会与 base_context 合并后作为最终请求上下文。
              </Typography>
            </Alert>
            <TextField
              label="base_context (JSON)"
              multiline
              minRows={10}
              value={baseContextText}
              onChange={(event) => setBaseContextText(event.target.value)}
              fullWidth
              helperText="填写该测试功能的基础上下文。建议从默认样例开始修改。"
            />
            <TextField
              label="base_context 默认例子 (只读)"
              multiline
              minRows={6}
              value={defaultBaseContextText}
              fullWidth
              InputProps={{ readOnly: true }}
            />
            <TextField
              label="injection (JSON)"
              multiline
              minRows={10}
              value={injectionText}
              onChange={(event) => setInjectionText(event.target.value)}
              fullWidth
              helperText="填写覆盖字段或新增字段。会覆盖同名 base_context 字段。"
            />
            <TextField
              label="injection 默认例子 (只读)"
              multiline
              minRows={4}
              value={defaultInjectionText}
              fullWidth
              InputProps={{ readOnly: true }}
            />
            <Stack direction="row" justifyContent="flex-start">
              <Button variant="contained" onClick={invokeFeature} disabled={invoking || (llmStatus?.available === false)}>
                {invoking ? "调用中..." : "手动调用"}
              </Button>
              <Button
                variant="outlined"
                onClick={() => {
                  setBaseContextText(defaultBaseContextText);
                  setInjectionText(defaultInjectionText);
                }}
                sx={{ ml: 1 }}
              >
                恢复默认例子
              </Button>
            </Stack>
          </Stack>
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardContent>
          <Stack spacing={1.5}>
            <Typography variant="h6">统计与审计</Typography>
            {!invokeResult ? (
              <Alert severity="info">尚未执行调用。</Alert>
            ) : (
              <>
                <Typography variant="body2" color="text.secondary">
                  status: {invokeResult.status} | test_run_id: {invokeResult.test_run_id}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  request_id: {invokeResult.request_id || "--"} | trace_id: {invokeResult.trace_id || "--"}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  请求次数(本次): {invokeResult.request_count} | token(本次): in {invokeResult.token_stats.input_tokens} / out {invokeResult.token_stats.output_tokens} / total {invokeResult.token_stats.total_tokens}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  请求次数(累计): {invokeResult.aggregate_request_count} | token(累计): in {invokeResult.aggregate_token_stats.input_tokens} / out {invokeResult.aggregate_token_stats.output_tokens} / total {invokeResult.aggregate_token_stats.total_tokens}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  测试日志: {invokeResult.audit_log_path || "--"}
                </Typography>
                <Stack direction="row">
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={() => void loadCurrentRunLog()}
                    disabled={llmStatus?.available === false}
                  >
                    显示当前测试详细日志
                  </Button>
                </Stack>
                <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                  {toPrettyJson(
                    stats
                      ? {
                          feature_stats: stats,
                          latest_run_summary: {
                            test_run_id: invokeResult.test_run_id,
                            request_count: invokeResult.request_count,
                            token_stats: invokeResult.token_stats,
                            trace_id: invokeResult.trace_id,
                          },
                        }
                      : invokeResult,
                  )}
                </pre>
              </>
            )}
          </Stack>
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardContent>
          <Stack spacing={1.5}>
            <Typography variant="h6">当前测试详细日志</Typography>
            {currentLogLoading ? (
              <Stack direction="row" spacing={1} alignItems="center">
                <CircularProgress size={18} />
                <Typography variant="body2">加载详细日志中...</Typography>
              </Stack>
            ) : currentLogError ? (
              <Alert severity="error">{currentLogError}</Alert>
            ) : !currentRunLog ? (
              <Alert severity="info">点击“显示当前测试详细日志”后在此展示。</Alert>
            ) : (
              <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                {toPrettyJson(currentRunLog)}
              </pre>
            )}
          </Stack>
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardContent>
          <Stack spacing={1.5}>
            <Typography variant="h6">最后一次 LLM 输入与输出</Typography>
            {!invokeResult || invokeResult.llm_calls.length === 0 ? (
              <Alert severity="info">当前功能未触发 LLM 调用，或暂无调用记录。</Alert>
            ) : (
              <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                {toPrettyJson(invokeResult.llm_calls[invokeResult.llm_calls.length - 1])}
              </pre>
            )}
          </Stack>
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardContent>
          <Stack spacing={1.5}>
            <Typography variant="h6">完整溯源与回放（审计事件）</Typography>
            {!invokeResult ? (
              <Alert severity="info">尚未执行调用。</Alert>
            ) : (
              <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                {toPrettyJson({
                  replay: invokeResult.replay,
                  recent_events: invokeResult.recent_events,
                  llm_calls: invokeResult.llm_calls,
                  effective_context: invokeResult.effective_context,
                  result: invokeResult.result,
                })}
              </pre>
            )}
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}
