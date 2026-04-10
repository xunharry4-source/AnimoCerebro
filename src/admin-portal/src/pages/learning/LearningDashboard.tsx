import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation();
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
        setError(e instanceof Error ? e.message : t("common.loadFailed"));
      }
    })();
  }, [loadPlan, loadHistory, t]);

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
      setError(e instanceof Error ? e.message : t("common.runFailed"));
    } finally {
      setLoading(false);
    }
  };

  const columns: GridColDef[] = [
    { field: "timestamp", headerName: t("learning.time"), width: 220 },
    { field: "kind", headerName: t("learning.kind"), width: 140 },
    { field: "direction", headerName: t("learning.direction"), width: 180 },
    {
      field: "verified",
      headerName: t("learning.verified"),
      width: 160,
      renderCell: (p) =>
        p.value ? <Chip label="VERIFIED" color="success" size="small" data-testid="verified-chip" /> : null,
    },
    { field: "architecture_ref", headerName: t("learning.archRef"), width: 100 },
    { field: "trace_id", headerName: "trace_id", flex: 1, minWidth: 200 },
    { field: "summary", headerName: t("learning.summary"), flex: 1.5, minWidth: 240 },
  ];

  return (
    <Stack spacing={2}>
      <Typography variant="h5">{t("learning.title")}</Typography>
      <Typography variant="body2" color="text.secondary">
        {t("learning.subtitle")}
      </Typography>

      {error ? (
        <Alert severity="error" data-testid="learning-error">
          {error}
        </Alert>
      ) : null}

      {plan ? (
        <Paper sx={{ p: 2 }}>
          <Typography variant="subtitle1" gutterBottom>
            {t("learning.redlineSummary")}
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
            <InputLabel id="dir-label">{t("learning.directionLabel")}</InputLabel>
            <Select
              labelId="dir-label"
              label={t("learning.directionLabel")}
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
            {t("learning.runCycleLlm")}
          </Button>
          <Button variant="outlined" disabled={loading} onClick={() => void runCycle(true)}>
            {t("learning.dryRun")}
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
