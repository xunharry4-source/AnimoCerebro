import { Alert, Box, Card, CardContent, Chip, Stack, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import { fetchJson } from "./api";
import type { InteractionMindState, OverviewPayload } from "./types";

type InteractionMindPayload = { state: InteractionMindState };

export default function InteractionMindPage() {
  const [data, setData] = useState<InteractionMindState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);

      try {
        const overview = await fetchJson<OverviewPayload>("/api/web/overview");
        const entityId = overview.session?.session_id || "web-console";
        const payload = await fetchJson<InteractionMindPayload>(
          `/api/web/interaction-mind/${encodeURIComponent(entityId)}`,
        );
        if (active) {
          setData(payload.state);
        }
      } catch {
        if (active) {
          setError("交互心智模块加载失败");
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
        <Typography variant="h4">交互心智模块</Typography>
        {loading ? <Typography color="text.secondary">加载中...</Typography> : null}
        {error ? <Alert severity="error">{error}</Alert> : null}

        {!loading && !error && data ? (
          <Card>
            <CardContent>
              <Typography variant="body1">角色: {data.model.role_hint}</Typography>
              <Typography variant="body1">目标假设: {data.model.current_goal_hypothesis}</Typography>
              <Typography variant="body1">
                误解风险: {Math.round((data.communication_fit.risk_of_misunderstanding || 0) * 100)}%
              </Typography>
              <Stack direction="row" spacing={1} sx={{ mt: 2 }} flexWrap="wrap" useFlexGap>
                {(data.misunderstanding_signals || []).length > 0 ? (
                  data.misunderstanding_signals.map((item) => (
                    <Chip key={item.signal_id} size="small" label={`${item.signal_type} (${item.severity})`} />
                  ))
                ) : (
                  <Chip size="small" label="暂无误解信号" />
                )}
              </Stack>
            </CardContent>
          </Card>
        ) : null}
      </Stack>
    </Box>
  );
}
