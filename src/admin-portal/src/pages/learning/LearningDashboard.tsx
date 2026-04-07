import {
  Alert,
  Box,
  Button,
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Typography,
} from "@mui/material";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";
import { useCallback, useEffect, useState } from "react";

type PlanDirection = {
  id: string;
  architecture_ref: string;
  title_zh: string;
  title_en: string;
  body_zh: string;
  body_en: string;
};

type HistoryRow = {
  id: string;
  entry_id: string;
  timestamp: string;
  trace_id: string;
  kind: string;
  direction: string;
  verified: boolean;
  summary: string;
  architecture_ref: string;
};

export default function LearningDashboard() {
  const [plan, setPlan] = useState<{ directions: PlanDirection[]; redlines: { zh: string; en: string } } | null>(
    null,
  );
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [direction, setDirection] = useState<string>("g24_curiosity");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastRun, setLastRun] = useState<string | null>(null);

  const loadPlan = useCallback(async () => {
    const res = await fetch("/api/web/learning/plan");
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<{ directions: PlanDirection[]; redlines: { zh: string; en: string } }>;
  }, []);

  const loadHistory = useCallback(async () => {
    const res = await fetch("/api/web/learning/history?limit=200");
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    const list = (data.rows as Omit<HistoryRow, "id">[]).map((r) => ({ ...r, id: r.entry_id }));
    setRows(list);
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        setError(null);
        const p = await loadPlan();
        setPlan(p);
        await loadHistory();
      } catch (e) {
        setError(e instanceof Error ? e.message : "加载失败");
      }
    })();
  }, [loadPlan, loadHistory]);

  const runCycle = async (dryRun: boolean) => {
    setLoading(true);
    setError(null);
    setLastRun(null);
    try {
      const res = await fetch("/api/web/learning/run-cycle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ direction, dry_run: dryRun, load_factor: 0 }),
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(t || res.statusText);
      }
      const body = await res.json();
      setLastRun(`status=${body.status} trace=${body.trace_id}`);
      await loadHistory();
    } catch (e) {
      setError(e instanceof Error ? e.message : "运行失败");
    } finally {
      setLoading(false);
    }
  };

  const columns: GridColDef[] = [
    { field: "timestamp", headerName: "时间 / Time", width: 220 },
    { field: "kind", headerName: "阶段 / Kind", width: 140 },
    { field: "direction", headerName: "方向 / Direction", width: 180 },
    {
      field: "verified",
      headerName: "已验证升格 / Verified",
      width: 160,
      renderCell: (p) =>
        p.value ? <Chip label="VERIFIED" color="success" size="small" data-testid="verified-chip" /> : null,
    },
    { field: "architecture_ref", headerName: "架构锚点 / Ref", width: 100 },
    { field: "trace_id", headerName: "trace_id", flex: 1, minWidth: 200 },
    { field: "summary", headerName: "摘要 / Summary", flex: 1.5, minWidth: 240 },
  ];

  return (
    <Stack spacing={2}>
      <Typography variant="h5">受控学习看板 / Controlled learning</Typography>
      <Typography variant="body2" color="text.secondary">
        中文：学习事件仅追加写入 BrainTranscriptStore，全程 trace_id 溯源；非 dry-run 路径强制 ModelProvider，失败即中断。
        <br />
        English: Learning events are append-only with trace_id; non-dry-run cycles require ModelProvider (no regex
        fakery).
      </Typography>

      {error ? (
        <Alert severity="error" data-testid="learning-error">
          {error}
        </Alert>
      ) : null}

      {plan ? (
        <Paper sx={{ p: 2 }}>
          <Typography variant="subtitle1" gutterBottom>
            红线摘要 / Redlines
          </Typography>
          <Typography variant="body2">{plan.redlines.zh}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            {plan.redlines.en}
          </Typography>
        </Paper>
      ) : null}

      <Paper sx={{ p: 2 }}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center">
          <FormControl sx={{ minWidth: 280 }}>
            <InputLabel id="dir-label">学习方向 / Direction</InputLabel>
            <Select
              labelId="dir-label"
              label="学习方向 / Direction"
              value={direction}
              onChange={(e) => setDirection(e.target.value)}
            >
              {(plan?.directions ?? []).map((d) => (
                <MenuItem key={d.id} value={d.id}>
                  {d.architecture_ref} — {d.title_zh} / {d.title_en}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Button variant="contained" disabled={loading} onClick={() => void runCycle(false)}>
            运行学习周期（需 LLM）/ Run cycle (LLM)
          </Button>
          <Button variant="outlined" disabled={loading} onClick={() => void runCycle(true)}>
            Dry-run（仅记事件）/ Dry-run
          </Button>
        </Stack>
        {lastRun ? (
          <Typography variant="caption" sx={{ mt: 1, display: "block" }}>
            {lastRun}
          </Typography>
        ) : null}
      </Paper>

      <Box sx={{ height: 520, width: "100%" }}>
        <DataGrid rows={rows} columns={columns} pageSizeOptions={[25, 50, 100]} disableRowSelectionOnClick />
      </Box>
    </Stack>
  );
}
