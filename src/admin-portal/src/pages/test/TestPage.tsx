import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation();
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
          setLlmHint(status.available ? null : (status.hint ?? t("test.llmUnavailable", { reason: status.reason ?? "unknown" })));
        } catch {
          setLlmAvailable(false);
          setLlmHint(t("test.llmStatusCheckFailed"));
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
        setError(t("test.catalogLoadFailed"));
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
      setHistoryError(t("test.historyLoadFailed"));
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
      setRunLogError(t("test.runLogLoadFailed"));
    } finally {
      setRunLogLoading(false);
    }
  };

  return (
    <Stack spacing={2}>
      <Typography variant="h4" component="h1">
        {t("test.title")}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {t("test.subtitle")}
      </Typography>
      {llmAvailable === false ? (
        <Alert severity="error">
          {t("test.llmDisabled")}{llmHint ? ` (${llmHint})` : ""}
        </Alert>
      ) : null}
      <Card variant="outlined">
        <CardContent>
          {loading ? (
            <Stack direction="row" spacing={1} alignItems="center">
              <CircularProgress size={18} />
              <Typography variant="body2">{t("common.loading")}</Typography>
            </Stack>
          ) : error ? (
            <Alert severity="error">{error}</Alert>
          ) : (
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>{t("test.featureName")}</TableCell>
                  <TableCell>{t("test.featureDescription")}</TableCell>
                  <TableCell width={240}>{t("common.actions")}</TableCell>
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
                        {t("test.enter")}
                      </Button>
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() => void loadFeatureHistory(feature.feature_id)}
                        sx={{ ml: 1 }}
                        disabled={llmAvailable === false}
                      >
                        {t("test.viewHistory")}
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
              <Typography variant="h6">{t("test.historyTitle", { featureId: selectedFeatureId })}</Typography>
              {historyLoading ? (
                <Stack direction="row" spacing={1} alignItems="center">
                  <CircularProgress size={18} />
                  <Typography variant="body2">{t("test.loadingHistory")}</Typography>
                </Stack>
              ) : historyError ? (
                <Alert severity="error">{historyError}</Alert>
              ) : historyItems.length === 0 ? (
                <Alert severity="info">{t("test.noHistoryRecords")}</Alert>
              ) : (
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>{t("test.testRunId")}</TableCell>
                      <TableCell>{t("test.startTime")}</TableCell>
                      <TableCell>{t("test.requestTokenStats")}</TableCell>
                      <TableCell width={140}>{t("common.actions")}</TableCell>
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
                            {t("test.viewLog")}
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
                  <Typography variant="body2">{t("test.loadingLog")}</Typography>
                </Stack>
              ) : runLogError ? (
                <Alert severity="error">{runLogError}</Alert>
              ) : selectedRunLog ? (
                <Stack spacing={1}>
                  <Typography variant="subtitle1">{t("test.logDetailTitle", { runId: selectedRunLog.item.test_run_id })}</Typography>
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
