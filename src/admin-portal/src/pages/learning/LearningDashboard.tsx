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
import ArticleIcon from "@mui/icons-material/Article";
import { Play } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { FIXED_LEARNING_QUESTIONS } from "../shared/fixedReflectionLearningQuestions";

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
  session_id: string;
  replay_event_id: string;
  kind: string;
  direction: string;
  verified: boolean;
  summary: string;
  architecture_ref: string;
  question_driver_refs: string[];
};

type LearningHistoryResponse = {
  rows: Omit<HistoryRow, "id">[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
};

type LearningMaintenancePayload = {
  started: boolean;
  forced: boolean;
  trace_id: string;
  used_memory_count: number;
  used_reflection_count: number;
  deleted_entry_count: number;
  summary: string;
};

function formatLearningTime(value: string): string {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

export default function LearningDashboard() {
  const { t } = useTranslation();
  const [plan, setPlan] = useState<{ directions: PlanDirection[]; redlines: { zh: string; en: string } } | null>(
    null,
  );
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [direction, setDirection] = useState<string>("g24_curiosity");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [maintenanceLoading, setMaintenanceLoading] = useState(false);
  const [lastRun, setLastRun] = useState<string | null>(null);
  const [lastMaintenance, setLastMaintenance] = useState<LearningMaintenancePayload | null>(null);
  const [paginationModel, setPaginationModel] = useState({ page: 0, pageSize: 25 });
  const [rowCount, setRowCount] = useState(0);

  const loadPlan = useCallback(async () => {
    const res = await fetch("/api/web/learning/plan");
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<{ directions: PlanDirection[]; redlines: { zh: string; en: string } }>;
  }, []);

  const loadHistory = useCallback(async (page: number, pageSize: number) => {
    setHistoryLoading(true);
    try {
      const res = await fetch(`/api/web/learning/history?page=${page + 1}&page_size=${pageSize}`);
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as LearningHistoryResponse;
      const list = data.rows.map((r) => ({ ...r, id: r.entry_id }));
      setRows(list);
      setRowCount(data.total_items);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        setError(null);
        const p = await loadPlan();
        setPlan(p);
      } catch (e) {
        setError(e instanceof Error ? e.message : t("common.loadFailed"));
      }
    })();
  }, [loadPlan, t]);

  useEffect(() => {
    void (async () => {
      try {
        setError(null);
        await loadHistory(paginationModel.page, paginationModel.pageSize);
      } catch (e) {
        setError(e instanceof Error ? e.message : t("common.loadFailed"));
      }
    })();
  }, [loadHistory, paginationModel.page, paginationModel.pageSize, t]);

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
      if (paginationModel.page === 0) {
        await loadHistory(0, paginationModel.pageSize);
      } else {
        setPaginationModel((current) => ({ ...current, page: 0 }));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.runFailed"));
    } finally {
      setLoading(false);
    }
  };

  const forceAutoOrganize = async () => {
    setMaintenanceLoading(true);
    setError(null);
    setLastMaintenance(null);
    try {
      const res = await fetch("/api/web/learning/maintenance/trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force: true }),
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = payload?.detail;
        const message =
          typeof detail === "string"
            ? detail
            : detail?.operator_message || detail?.message || t("learning.forceAutoOrganizeFailed");
        throw new Error(message);
      }
      setLastMaintenance(payload as LearningMaintenancePayload);
      setLastRun(`maintenance trace=${payload.trace_id}`);
      if (paginationModel.page === 0) {
        await loadHistory(0, paginationModel.pageSize);
      } else {
        setPaginationModel((current) => ({ ...current, page: 0 }));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("learning.forceAutoOrganizeFailed"));
    } finally {
      setMaintenanceLoading(false);
    }
  };

  const columns: GridColDef[] = [
    {
      field: "timestamp",
      headerName: t("learning.time"),
      width: 220,
      renderCell: (p) => formatLearningTime(String(p.value || "")),
    },
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
    {
      field: "question_driver_refs",
      headerName: "问题关联",
      minWidth: 220,
      flex: 1,
      renderCell: (p) => {
        const refs = Array.isArray(p.value) ? (p.value as string[]) : [];
        if (refs.length === 0) {
          return <Typography variant="caption" color="text.secondary">无</Typography>;
        }
        return (
          <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap" sx={{ py: 0.5 }}>
            {refs.map((ref) => (
              <Chip
                key={`${p.row.entry_id}-${ref}`}
                label={ref}
                size="small"
                component={RouterLink}
                to={`/console/nine-questions/${ref}`}
                clickable
              />
            ))}
          </Stack>
        );
      },
    },
    { field: "summary", headerName: t("learning.summary"), flex: 1.5, minWidth: 240 },
    {
      field: "actions",
      headerName: "溯源",
      minWidth: 220,
      sortable: false,
      filterable: false,
      renderCell: (p) => (
        <Stack direction="row" spacing={1} sx={{ py: 0.5 }}>
          <Button
            size="small"
            variant="outlined"
            component={RouterLink}
            to={`/console/audit/transcript-replay/${encodeURIComponent(String(p.row.replay_event_id || p.row.trace_id))}`}
          >
            查看 trace
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
        <Box>
          <Typography variant="h5">{t("learning.title")}</Typography>
          <Typography variant="body2" color="text.secondary">
            {t("learning.subtitle")}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
          <Button
            variant="contained"
            startIcon={<Play size={16} />}
            disabled={maintenanceLoading}
            onClick={() => void forceAutoOrganize()}
          >
            {maintenanceLoading ? t("common.processing") : t("learning.forceAutoOrganize")}
          </Button>
          <Button
            component={RouterLink}
            to="/console/module-logs/learning"
            variant="outlined"
            startIcon={<ArticleIcon />}
          >
            {t("moduleLogs.view")}
          </Button>
        </Stack>
      </Stack>

      {error ? (
        <Alert severity="error" data-testid="learning-error">
          {error}
        </Alert>
      ) : null}

      {lastMaintenance ? (
        <Alert severity="success" variant="outlined">
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
            <Typography variant="body2">{lastMaintenance.summary}</Typography>
            <Chip size="small" label={`trace=${lastMaintenance.trace_id}`} />
            <Chip size="small" label={`memory=${lastMaintenance.used_memory_count}`} />
            <Chip size="small" label={`reflection=${lastMaintenance.used_reflection_count}`} />
          </Stack>
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
        <Typography variant="subtitle1" gutterBottom>
          学习固定问题
        </Typography>
        <Stack spacing={1}>
          {FIXED_LEARNING_QUESTIONS.map((question, index) => (
            <Typography key={question} variant="body2">
              {index + 1}. {question}
            </Typography>
          ))}
        </Stack>
      </Paper>

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
        <DataGrid
          rows={rows}
          columns={columns}
          pageSizeOptions={[25, 50, 100]}
          paginationMode="server"
          paginationModel={paginationModel}
          onPaginationModelChange={setPaginationModel}
          rowCount={rowCount}
          loading={historyLoading}
          disableRowSelectionOnClick
        />
      </Box>
    </Stack>
  );
}
