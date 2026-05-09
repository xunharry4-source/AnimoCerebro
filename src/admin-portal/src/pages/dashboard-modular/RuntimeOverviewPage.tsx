import { Box, Card, CardContent, Chip, List, ListItem, ListItemText, Stack, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import ModuleStatusBanner from "./ModuleStatusBanner";
import {
  fetchJsonWithTimeout,
  normalizeModuleError,
  runWithRetry,
  type ModuleErrorInfo,
} from "./moduleRequest";
import type { OverviewPayload } from "./types";

export default function RuntimeOverviewPage() {
  const [data, setData] = useState<OverviewPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ModuleErrorInfo | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const load = async (active: { value: boolean }) => {
    setLoading(true);
    setError(null);
    try {
      const payload = await runWithRetry(
        () => fetchJsonWithTimeout<OverviewPayload>("/api/web/overview"),
        1,
      );
      if (active.value) {
        setData(payload);
      }
    } catch (e) {
      if (active.value) {
        setError(normalizeModuleError(e, "运行时总览加载失败"));
      }
    } finally {
      if (active.value) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    const active = { value: true };
    void load(active);
    return () => {
      active.value = false;
    };
  }, [reloadToken]);

  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={2}>
        <Typography variant="h4">运行时总览模块</Typography>
        <ModuleStatusBanner
          loading={loading}
          error={error}
          onRetry={() => setReloadToken((v) => v + 1)}
        />

        {!loading && !error && data ? (
          <>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Runtime
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  <Chip label={`runtime_id: ${data.runtime.runtime_id}`} />
                  <Chip label={`degraded: ${String(data.runtime.degraded_mode)}`} color={data.runtime.degraded_mode ? "warning" : "success"} />
                  <Chip label={`memory: ${data.runtime.memory_store_status}`} />
                  <Chip label={`transcript: ${data.runtime.transcript_store_status}`} />
                </Stack>
              </CardContent>
            </Card>

            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  当前关注
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {data.working_memory.current_focus_summary || "暂无总结"}
                </Typography>
                <List dense>
                  {(data.working_memory.active_focus_titles || []).length > 0 ? (
                    (data.working_memory.active_focus_titles || []).map((title) => (
                      <ListItem key={title}>
                        <ListItemText primary={title} />
                      </ListItem>
                    ))
                  ) : (
                    <ListItem>
                      <ListItemText primary="暂无 active_focus_titles" />
                    </ListItem>
                  )}
                </List>
              </CardContent>
            </Card>
          </>
        ) : null}
      </Stack>
    </Box>
  );
}
