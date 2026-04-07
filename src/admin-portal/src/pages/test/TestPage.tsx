import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { fetchLlmStatus } from "../../api/llmStatus";

export type ModelFeatureCatalogItem = {
  feature_id: string;
  feature_name: string;
  description: string;
  default_payload: {
    base_context?: Record<string, unknown>;
    injection?: Record<string, unknown>;
  };
};

type HistoryItem = {
  test_run_id: string;
  feature_id: string;
  feature_name: string;
  started_at: string;
  finished_at: string;
  status: string;
  trace_id: string | null;
  request_id: string | null;
  request_count: number;
  token_stats: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
};

type RunLogResponse = {
  item: HistoryItem;
  log: Record<string, unknown>;
  replay: Record<string, unknown> | null;
  recent_events: Array<Record<string, unknown>>;
};

type TestPageProps = {
  onNavigate: (pageId: `test-feature:${string}`) => void;
};

export default function TestPage({ onNavigate }: TestPageProps) {
  const [items, setItems] = useState<ModelFeatureCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [llmAvailable, setLlmAvailable] = useState<boolean | null>(null);
  const [llmHint, setLlmHint] = useState<string | null>(null);
  const [selectedFeatureId, setSelectedFeatureId] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyItems, setHistoryItems] = useState<HistoryItem[]>([]);
  const [runLogLoading, setRunLogLoading] = useState(false);
  const [runLogError, setRunLogError] = useState<string | null>(null);
  const [selectedRunLog, setSelectedRunLog] = useState<RunLogResponse | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        try {
          const status = await fetchLlmStatus(true);
          setLlmAvailable(status.available);
          setLlmHint(status.available ? null : (status.hint ?? `LLM 不可用：${status.reason ?? "unknown"}`));
        } catch {
          setLlmAvailable(false);
          setLlmHint("LLM 状态检查失败，请检查后端。");
        }

        const response = await fetch("/api/web/tests/model-features", {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error("catalog_load_failed");
        }
        setItems((await response.json()) as ModelFeatureCatalogItem[]);
        setError(null);
      } catch {
        setError("无法加载模型功能测试清单，请检查后端状态。");
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  const loadFeatureHistory = async (featureId: string) => {
    setSelectedFeatureId(featureId);
    setHistoryLoading(true);
    setSelectedRunLog(null);
    setRunLogError(null);
    try {
      const response = await fetch(
        `/api/web/tests/model-features/${encodeURIComponent(featureId)}/history?limit=30`,
        { headers: { Accept: "application/json" } },
      );
      if (!response.ok) {
        throw new Error("history_load_failed");
      }
      setHistoryItems((await response.json()) as HistoryItem[]);
      setHistoryError(null);
    } catch {
      setHistoryItems([]);
      setHistoryError("无法加载该功能的历史测试记录。");
    } finally {
      setHistoryLoading(false);
    }
  };

  const loadRunLog = async (testRunId: string) => {
    setRunLogLoading(true);
    try {
      const response = await fetch(
        `/api/web/tests/model-features/runs/${encodeURIComponent(testRunId)}`,
        { headers: { Accept: "application/json" } },
      );
      if (!response.ok) {
        throw new Error("run_log_failed");
      }
      setSelectedRunLog((await response.json()) as RunLogResponse);
      setRunLogError(null);
    } catch {
      setSelectedRunLog(null);
      setRunLogError("无法加载该条测试记录的详细日志。");
    } finally {
      setRunLogLoading(false);
    }
  };

  return (
    <Stack spacing={2}>
      <Typography variant="h4" component="h1">
        测试页面
      </Typography>
      <Typography variant="body2" color="text.secondary">
        当前列出所有已接入大模型调用的可测试功能，支持手动注入参数并观察输出效果。
      </Typography>
      {llmAvailable === false ? (
        <Alert severity="error">
          LLM 不可用，已禁止所有测试功能操作。{llmHint ? ` (${llmHint})` : ""}
        </Alert>
      ) : null}
      <Card variant="outlined">
        <CardContent>
          {loading ? (
            <Stack direction="row" spacing={1} alignItems="center">
              <CircularProgress size={18} />
              <Typography variant="body2">加载中...</Typography>
            </Stack>
          ) : error ? (
            <Alert severity="error">{error}</Alert>
          ) : (
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>测试功能名</TableCell>
                  <TableCell>功能说明</TableCell>
                  <TableCell width={240}>操作</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {items.map((feature) => (
                  <TableRow key={feature.feature_id} hover>
                    <TableCell>{feature.feature_name}</TableCell>
                    <TableCell>{feature.description}</TableCell>
                    <TableCell>
                      <Button
                        size="small"
                        variant="contained"
                        onClick={() => onNavigate(`test-feature:${feature.feature_id}`)}
                        disabled={llmAvailable === false}
                      >
                        进入
                      </Button>
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() => void loadFeatureHistory(feature.feature_id)}
                        sx={{ ml: 1 }}
                        disabled={llmAvailable === false}
                      >
                        查看历史
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {selectedFeatureId ? (
        <Card variant="outlined">
          <CardContent>
            <Stack spacing={2}>
              <Typography variant="h6">历史测试记录：{selectedFeatureId}</Typography>
              {historyLoading ? (
                <Stack direction="row" spacing={1} alignItems="center">
                  <CircularProgress size={18} />
                  <Typography variant="body2">加载历史记录中...</Typography>
                </Stack>
              ) : historyError ? (
                <Alert severity="error">{historyError}</Alert>
              ) : historyItems.length === 0 ? (
                <Alert severity="info">该功能暂无历史测试记录。</Alert>
              ) : (
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>测试运行ID</TableCell>
                      <TableCell>开始时间</TableCell>
                      <TableCell>请求/Token</TableCell>
                      <TableCell width={140}>操作</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {historyItems.map((item) => (
                      <TableRow key={item.test_run_id} hover>
                        <TableCell>{item.test_run_id}</TableCell>
                        <TableCell>{item.started_at}</TableCell>
                        <TableCell>
                          {item.request_count} 次 / {item.token_stats.total_tokens} tokens
                        </TableCell>
                        <TableCell>
                          <Button
                            size="small"
                            variant="outlined"
                            onClick={() => void loadRunLog(item.test_run_id)}
                            disabled={llmAvailable === false}
                          >
                            查看日志
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}

              {runLogLoading ? (
                <Stack direction="row" spacing={1} alignItems="center">
                  <CircularProgress size={18} />
                  <Typography variant="body2">加载日志中...</Typography>
                </Stack>
              ) : runLogError ? (
                <Alert severity="error">{runLogError}</Alert>
              ) : selectedRunLog ? (
                <Stack spacing={1}>
                  <Typography variant="subtitle1">记录详细日志：{selectedRunLog.item.test_run_id}</Typography>
                  <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                    {JSON.stringify(selectedRunLog, null, 2)}
                  </pre>
                </Stack>
              ) : null}
            </Stack>
          </CardContent>
        </Card>
      ) : null}
    </Stack>
  );
}
