import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import { Link as RouterLink, useParams } from "react-router-dom";

type ReplayEvent = {
  entry_id: string;
  entry_type: string;
  timestamp: string;
  trace_id: string;
  source?: string;
  payload?: unknown;
};

type TranscriptReplayPayload = {
  event_id: string;
  trace_id: string;
  summary: string;
  source_module?: string | null;
  invocation_phase?: string | null;
  question_driver_refs: string[];
  events: ReplayEvent[];
};

export default function TranscriptReplayPage() {
  const { event_id: eventId = "" } = useParams();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<TranscriptReplayPayload | null>(null);

  useEffect(() => {
    void loadReplay();
  }, [eventId]);

  const loadReplay = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`/api/web/replay/${encodeURIComponent(eventId)}`);
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        const detail =
          (typeof data?.detail === "string" && data.detail) ||
          (typeof data?.message === "string" && data.message) ||
          `获取 transcript 回放失败（HTTP ${resp.status}）`;
        throw new Error(detail);
      }
      setPayload(data as TranscriptReplayPayload);
    } catch (err: any) {
      setError(err?.message || "获取 transcript 回放失败");
      setPayload(null);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <CircularProgress />;
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  if (!payload) {
    return <Alert severity="info">没有可用的 transcript 回放数据。</Alert>;
  }

  return (
    <Stack spacing={2} data-testid="transcript-replay-page">
      <Box>
        <Typography variant="h4" gutterBottom>
          Transcript 回放
        </Typography>
        <Typography variant="body2" color="text.secondary">
          这里显示的是按 trace 聚合后的真实 transcript 事件链，不是页面层拼接摘要。
        </Typography>
      </Box>

      <Card variant="outlined">
        <CardContent>
          <Stack spacing={1.5}>
            <Typography variant="h6">{payload.summary}</Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              <Chip label={`trace: ${payload.trace_id}`} variant="outlined" sx={{ fontFamily: "monospace" }} />
              {payload.source_module ? <Chip label={`source: ${payload.source_module}`} variant="outlined" /> : null}
              {payload.invocation_phase ? <Chip label={`phase: ${payload.invocation_phase}`} variant="outlined" /> : null}
              <Chip label={`events: ${payload.events.length}`} color="primary" />
            </Stack>
            {payload.question_driver_refs.length > 0 ? (
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                {payload.question_driver_refs.map((ref) => (
                  <Chip
                    key={ref}
                    label={`驱动: ${ref}`}
                    component={RouterLink}
                    to={`/console/nine-questions/${ref}`}
                    clickable
                    size="small"
                  />
                ))}
              </Stack>
            ) : null}
          </Stack>
        </CardContent>
      </Card>

      <Stack spacing={1.2}>
        {payload.events.map((event) => (
          <Card key={event.entry_id} variant="outlined">
            <CardContent>
              <Stack spacing={0.8}>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
                  <Chip label={event.entry_type} size="small" color="primary" />
                  <Typography variant="caption" color="text.secondary">
                    {event.timestamp}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {event.source || "-"}
                  </Typography>
                </Stack>
                <Typography variant="body2" sx={{ fontFamily: "monospace", wordBreak: "break-all" }}>
                  entry_id: {event.entry_id}
                </Typography>
                <Box
                  component="pre"
                  sx={{
                    p: 1.5,
                    bgcolor: "grey.100",
                    borderRadius: 1,
                    overflow: "auto",
                    fontSize: "0.75rem",
                    m: 0,
                  }}
                >
                  {JSON.stringify(event.payload ?? {}, null, 2)}
                </Box>
              </Stack>
            </CardContent>
          </Card>
        ))}
      </Stack>
    </Stack>
  );
}
