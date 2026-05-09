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
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import {
  type Locale,
  auditReplayCopy,
} from "../../i18n";
import { useTranslation } from "react-i18next";

type ModelProviderTrace = {
  trace_id: string;
  request_id: string;
  decision_id: string;
  phase_name: string;
  session_id: string;
  turn_id: string;
  provider_plugin_id: string;
  provider_name: string | null;
  model: string | null;
  source_module: string | null;
  invocation_phase: string | null;
  question_driver_refs: string[];
  invoked_at: string | null;
  completed_at: string | null;
  failed_at: string | null;
  prompt: string | null;
  context: Record<string, unknown>;
  request_driver: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error_type: string | null;
  error_message: string | null;
  related_events: Array<{
    entry_id: string;
    session_id: string;
    turn_id: string;
    entry_type: string;
    timestamp: string;
    source: string;
    trace_id: string;
    payload: unknown;
  }>;
};

function traceStatus(
  trace: ModelProviderTrace,
  text: (typeof auditReplayCopy)[Locale],
) {
  if (trace.failed_at) {
    return { label: text.failed, color: "error" as const };
  }
  if (trace.completed_at) {
    return { label: text.succeeded, color: "success" as const };
  }
  return { label: text.pending, color: "warning" as const };
}

export default function AuditReplay() {
  const { t, i18n } = useTranslation();
  const [locale, setLocale] = useState<Locale>(i18n.language as Locale || "zh-CN");
  const [requestId, setRequestId] = useState("");
  const [decisionId, setDecisionId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [traces, setTraces] = useState<ModelProviderTrace[]>([]);
  const text = auditReplayCopy[locale];

  const loadTraces = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (requestId.trim()) {
        params.set("request_id", requestId.trim());
      }
      if (decisionId.trim()) {
        params.set("decision_id", decisionId.trim());
      }
      const response = await fetch(`/api/web/audit/model-provider?${params.toString()}`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error("audit_failed");
      }
      setTraces((await response.json()) as ModelProviderTrace[]);
      setError(null);
    } catch {
      setError(text.backendError);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadTraces();
  }, []);

  return (
    <Stack spacing={3}>
      <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
        <Box>
          <Typography variant="h4" component="h1" gutterBottom>
            {t("audit.title")}
          </Typography>
          <Typography variant="body1" color="text.secondary">
            {t("audit.subtitle")}
          </Typography>
        </Box>
        <FormControl sx={{ minWidth: 140 }}>
          <InputLabel id="audit-language-label">{t("common.language")}</InputLabel>
          <Select
            labelId="audit-language-label"
            value={locale}
            label={t("common.language")}
            onChange={(event) => {
              const newLang = event.target.value as Locale;
              setLocale(newLang);
              i18n.changeLanguage(newLang);
            }}
          >
            <MenuItem value="zh-CN">中文</MenuItem>
            <MenuItem value="en-US">English</MenuItem>
          </Select>
        </FormControl>
      </Stack>

      <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
        <TextField
          label={t("audit.requestId")}
          value={requestId}
          onChange={(event) => setRequestId(event.target.value)}
          fullWidth
        />
        <TextField
          label={t("audit.decisionId")}
          value={decisionId}
          onChange={(event) => setDecisionId(event.target.value)}
          fullWidth
        />
        <Button variant="contained" onClick={() => void loadTraces()} disabled={loading}>
          {loading ? t("common.refreshing") : t("audit.search")}
        </Button>
      </Stack>

      {error ? <Alert severity="error">{error}</Alert> : null}

      {traces.length === 0 && !loading ? (
        <Card>
          <CardContent>
            <Typography variant="body2" color="text.secondary">
              {t("audit.empty")}
            </Typography>
          </CardContent>
        </Card>
      ) : null}

      {traces.map((trace) => {
        const status = traceStatus(trace, text);
        return (
          <Accordion key={trace.trace_id}>
            <AccordionSummary>
              <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
                <Chip label={status.label} color={status.color} size="small" />
                <Typography variant="subtitle2">{trace.provider_name || trace.provider_plugin_id}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {trace.model}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {trace.phase_name}
                </Typography>
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={2}>
                <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      {t("audit.traceId")}
                    </Typography>
                    <Typography variant="body2">{trace.trace_id}</Typography>
                  </Box>
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      {t("audit.recordedAt")}
                    </Typography>
                    <Typography variant="body2">{trace.invoked_at || "--"}</Typography>
                  </Box>
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      {t("audit.sourceModule")}
                    </Typography>
                    <Typography variant="body2">{trace.source_module || "--"}</Typography>
                  </Box>
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      {t("audit.invocationPhase")}
                    </Typography>
                    <Typography variant="body2">{trace.invocation_phase || "--"}</Typography>
                  </Box>
                </Stack>
                {trace.question_driver_refs.length > 0 && (
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      {t("audit.questionDriverRefs")}
                    </Typography>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
                      {trace.question_driver_refs.map((ref) => (
                        <Chip key={ref} size="small" label={ref} variant="outlined" />
                      ))}
                    </Stack>
                  </Box>
                )}
                {trace.error_message && (
                  <Alert severity="error">
                    <Typography variant="caption">{trace.error_type}</Typography>
                    <Typography variant="body2">{trace.error_message}</Typography>
                  </Alert>
                )}
                {trace.related_events.length > 0 && (
                  <Box>
                    <Typography variant="subtitle2" gutterBottom>
                      {t("audit.relatedEvents")}
                    </Typography>
                    <Stack spacing={1}>
                      {trace.related_events.map((event) => (
                        <Card key={event.entry_id} variant="outlined">
                          <CardContent sx={{ py: 1 }}>
                            <Typography variant="caption" color="text.secondary">
                              {event.entry_type} · {event.timestamp}
                            </Typography>
                          </CardContent>
                        </Card>
                      ))}
                    </Stack>
                  </Box>
                )}
                <Box>
                  <Typography variant="subtitle2" gutterBottom>
                    {t("audit.requestJson")}
                  </Typography>
                  <Box
                    component="pre"
                    sx={{
                      p: 2,
                      bgcolor: "grey.100",
                      borderRadius: 1,
                      overflow: "auto",
                      fontSize: "0.75rem",
                    }}
                  >
                    {JSON.stringify(trace.prompt ? { prompt: trace.prompt, context: trace.context } : trace.context, null, 2)}
                  </Box>
                </Box>
                {trace.result && (
                  <Box>
                    <Typography variant="subtitle2" gutterBottom>
                      {t("audit.responseJson")}
                    </Typography>
                    <Box
                      component="pre"
                      sx={{
                        p: 2,
                        bgcolor: "grey.100",
                        borderRadius: 1,
                        overflow: "auto",
                        fontSize: "0.75rem",
                      }}
                    >
                      {JSON.stringify(trace.result, null, 2)}
                    </Box>
                  </Box>
                )}
              </Stack>
            </AccordionDetails>
          </Accordion>
        );
      })}
    </Stack>
  );
}
