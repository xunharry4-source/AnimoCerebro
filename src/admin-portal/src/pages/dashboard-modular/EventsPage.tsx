import {
  Alert,
  Box,
  Card,
  CardContent,
  List,
  ListItem,
  ListItemText,
  Stack,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import { fetchJson } from "./api";
import type { OverviewPayload } from "./types";

export default function EventsPage() {
  const [events, setEvents] = useState<OverviewPayload["recent_events"]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const payload = await fetchJson<OverviewPayload>("/api/web/overview");
        if (active) {
          setEvents(payload.recent_events || []);
        }
      } catch {
        if (active) {
          setError("事件流加载失败");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    void load();
    return () => {
      active = false;
    };
  }, []);

  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={2}>
        <Typography variant="h4">事件流模块</Typography>
        {loading ? <Typography color="text.secondary">加载中...</Typography> : null}
        {error ? <Alert severity="error">{error}</Alert> : null}

        {!loading && !error ? (
          <Card>
            <CardContent>
              <List dense>
                {(events || []).length > 0 ? (
                  (events || []).map((event) => (
                    <ListItem key={event.entry_id} divider>
                      <ListItemText
                        primary={`${event.entry_type} · ${event.source}`}
                        secondary={`${event.timestamp} · turn=${event.turn_id}`}
                      />
                    </ListItem>
                  ))
                ) : (
                  <ListItem>
                    <ListItemText primary="暂无事件" />
                  </ListItem>
                )}
              </List>
            </CardContent>
          </Card>
        ) : null}
      </Stack>
    </Box>
  );
}
