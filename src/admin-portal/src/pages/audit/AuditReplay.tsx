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
  const [locale, setLocale] = useState<Locale>("zh-CN");
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
            {text.title}
          </Typography>
          <Typography variant="body1" color="text.secondary">
            {text.subtitle}
          </Typography>
        </Box>
        <FormControl sx={{ minWidth: 140 }}>
          <InputLabel id="audit-language-label">Language</InputLabel>
          <Select
            labelId="audit-language-label"
            value={locale}
            label="Language"
            onChange={(event) => setLocale(event.target.value as Locale)}
          >
            <MenuItem value="zh-CN">中文</MenuItem>
            <MenuItem value="en-US">English</MenuItem>
          </Select>
        </FormControl>
      </Stack>

      <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
        <TextField
          label={text.requestId}
          value={requestId}
          onChange={(event) => setRequestId(event.target.value)}
          fullWidth
        />
        <TextField
          label={text.decisionId}
          value={decisionId}
          onChange={(event) => setDecisionId(event.target.value)}
          fullWidth
        />
        <Button variant="contained" onClick={() => void loadTraces()} disabled={loading}>
          {loading ? text.refreshing : text.search}
        </Button>
      </Stack>

      {error ? <Alert severity="error">{error}</Alert> : null}

      {traces.length === 0 ? (
        <Alert severity="info">{text.empty}</Alert>
      ) : (
        traces.map((trace) => {
          const status = traceStatus(trace, text);
          return (
            <Card key={trace.request_id} variant="outlined">
              <CardContent>
                <Stack spacing={2}>
                  <Stack direction={{ xs: "column", md: "row" }} spacing={1} useFlexGap flexWrap="wrap">
                    <Chip label={`${text.phase}: ${trace.phase_name}`} variant="outlined" />
                    <Chip label={`${text.provider}: ${trace.provider_name || trace.provider_plugin_id}`} variant="outlined" />
                    <Chip label={`${text.model}: ${trace.model || "--"}`} variant="outlined" />
                    <Chip label={status.label} color={status.color} />
                  </Stack>
                  <Typography variant="body2" color="text.secondary">
                    request_id: {trace.request_id}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    decision_id: {trace.decision_id}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    trace_id: {trace.trace_id}
                  </Typography>

                  <Accordion>
                    <AccordionSummary>
                      <Typography variant="subtitle2">{text.traceChain}</Typography>
                    </AccordionSummary>
                    <AccordionDetails>
                      <Stack spacing={1}>
                        <Typography variant="body2">
                          {text.traceId}: {trace.trace_id}
                        </Typography>
                        <Typography variant="body2">
                          {text.sourceModule}: {trace.source_module || "--"}
                        </Typography>
                        <Typography variant="body2">
                          {text.invocationPhase}: {trace.invocation_phase || trace.phase_name}
                        </Typography>
                        <Typography variant="body2">
                          {text.questionDriverRefs}:{" "}
                          {trace.question_driver_refs.length > 0
                            ? trace.question_driver_refs.join(" / ")
                            : "--"}
                        </Typography>
                        <Typography variant="body2">
                          {text.recordedAt}: {trace.invoked_at || trace.completed_at || trace.failed_at || "--"}
                        </Typography>
                        <Typography variant="body2">{text.relatedEvents}:</Typography>
                        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                          {trace.related_events.length > 0 ? (
                            trace.related_events.map((event) => (
                              <Chip
                                key={event.entry_id}
                                label={`${event.entry_type} @ ${event.timestamp}`}
                                variant="outlined"
                              />
                            ))
                          ) : (
                            <Chip label="--" variant="outlined" />
                          )}
                        </Stack>
                      </Stack>
                    </AccordionDetails>
                  </Accordion>

                  <Accordion>
                    <AccordionSummary>
                      <Typography variant="subtitle2">{text.requestDriver}</Typography>
                    </AccordionSummary>
                    <AccordionDetails>
                      <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                        {JSON.stringify(trace.request_driver, null, 2)}
                      </pre>
                    </AccordionDetails>
                  </Accordion>

                  <Accordion>
                    <AccordionSummary>
                      <Typography variant="subtitle2">{text.requestJson}</Typography>
                    </AccordionSummary>
                    <AccordionDetails>
                      <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                        {JSON.stringify(
                          {
                            prompt: trace.prompt,
                            context: trace.context,
                          },
                          null,
                          2,
                        )}
                      </pre>
                    </AccordionDetails>
                  </Accordion>

                  <Accordion>
                    <AccordionSummary>
                      <Typography variant="subtitle2">{text.responseJson}</Typography>
                    </AccordionSummary>
                    <AccordionDetails>
                      <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                        {JSON.stringify(trace.result, null, 2)}
                      </pre>
                    </AccordionDetails>
                  </Accordion>

                  {trace.error_message ? (
                    <Alert severity="error">
                      {text.error}: {trace.error_type} · {trace.error_message}
                    </Alert>
                  ) : null}
                </Stack>
              </CardContent>
            </Card>
          );
        })
      )}
    </Stack>
  );
}
