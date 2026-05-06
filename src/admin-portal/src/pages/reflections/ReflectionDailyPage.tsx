import { useCallback, useEffect, useMemo, useState } from "react";
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
  TextField,
  Typography,
} from "@mui/material";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";
import { Link as RouterLink, useSearchParams } from "react-router-dom";
import { Play } from "lucide-react";

type ReflectionRecord = {
  reflection_id: string;
  created_at: string;
  reflection_type?: string;
  subject?: string;
  summary?: string;
  trace_id?: string | null;
  audit_id?: string | null;
  context?: Record<string, any>;
  metadata?: Record<string, any>;
};

type ReflectionPage = {
  items: ReflectionRecord[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
  database_backed: boolean;
};

type ReflectionMaintenancePayload = {
  started: boolean;
  forced: boolean;
  trace_id: string;
  generated_reflection_id: string;
  used_memory_count: number;
  deleted_reflection_count: number;
  summary: string;
};

type SourceFilter = "all" | "plugin" | "nine_questions";

function localDateString(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDateTime(value: string): string {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function recordSource(row: ReflectionRecord): string {
  const metadataSource = String(row.metadata?.source || "").trim();
  if (metadataSource) return metadataSource;
  const contextSource = String(row.context?.source || row.context?.source_module || "").trim();
  if (contextSource) return contextSource;
  const questionId = String(row.context?.question_id || "").trim();
  if (questionId) return `nine_questions.${questionId}`;
  return "-";
}

async function fetchReflectionPage(params: {
  source: SourceFilter;
  date: string;
  page: number;
  pageSize: number;
}): Promise<ReflectionPage> {
  const query = new URLSearchParams({
    source: params.source,
    date: params.date,
    page: String(params.page + 1),
    page_size: String(params.pageSize),
  });
  const response = await fetch(`/api/web/reflections?${query.toString()}`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail =
      (typeof data?.detail === "string" && data.detail) ||
      (typeof data?.detail?.message === "string" && data.detail.message) ||
      `获取反思分页失败（HTTP ${response.status}）`;
    throw new Error(detail);
  }
  if (!Array.isArray(data?.items) || typeof data.total_items !== "number") {
    throw new Error("反思分页接口返回格式错误：期望 items 与 total_items。");
  }
  return data as ReflectionPage;
}

export default function ReflectionDailyPage({ initialSource = "all" }: { initialSource?: SourceFilter }) {
  const [searchParams] = useSearchParams();
  const requestedSource = searchParams.get("source") as SourceFilter | null;
  const [source, setSource] = useState<SourceFilter>(requestedSource || initialSource);
  const [date, setDate] = useState(searchParams.get("date") || localDateString(new Date()));
  const [rows, setRows] = useState<ReflectionRecord[]>([]);
  const [rowCount, setRowCount] = useState(0);
  const [paginationModel, setPaginationModel] = useState({ page: 0, pageSize: 25 });
  const [loading, setLoading] = useState(false);
  const [maintenanceLoading, setMaintenanceLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastMaintenance, setLastMaintenance] = useState<ReflectionMaintenancePayload | null>(null);
  const [databaseBacked, setDatabaseBacked] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchReflectionPage({
        source,
        date,
        page: paginationModel.page,
        pageSize: paginationModel.pageSize,
      });
      setRows(payload.items);
      setRowCount(payload.total_items);
      setDatabaseBacked(Boolean(payload.database_backed));
    } catch (err: any) {
      setRows([]);
      setRowCount(0);
      setDatabaseBacked(false);
      setError(err?.message || "获取反思分页失败");
    } finally {
      setLoading(false);
    }
  }, [date, paginationModel.page, paginationModel.pageSize, source]);

  useEffect(() => {
    void load();
  }, [load]);

  const forceAutoOrganize = async () => {
    setMaintenanceLoading(true);
    setError(null);
    setLastMaintenance(null);
    try {
      const response = await fetch("/api/web/reflections/maintenance/trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force: true }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = payload?.detail;
        const message =
          typeof detail === "string"
            ? detail
            : detail?.operator_message || detail?.message || "强制启动反思自动整理失败";
        throw new Error(message);
      }
      setLastMaintenance(payload as ReflectionMaintenancePayload);
      if (paginationModel.page === 0) {
        await load();
      } else {
        setPaginationModel((current) => ({ ...current, page: 0 }));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "强制启动反思自动整理失败");
    } finally {
      setMaintenanceLoading(false);
    }
  };

  const columns = useMemo<GridColDef[]>(
    () => [
      {
        field: "created_at",
        headerName: "时间",
        width: 190,
        renderCell: (params) => formatDateTime(String(params.value || "")),
      },
      { field: "reflection_type", headerName: "反思类型", width: 180 },
      {
        field: "source",
        headerName: "来源",
        width: 220,
        valueGetter: (_, row) => recordSource(row as ReflectionRecord),
      },
      { field: "subject", headerName: "主题", minWidth: 220, flex: 0.8 },
      { field: "summary", headerName: "当天发生了什么 / 反思摘要", minWidth: 320, flex: 1.5 },
      {
        field: "trace_id",
        headerName: "Trace",
        minWidth: 220,
        flex: 0.8,
        renderCell: (params) => {
          const traceId = String(params.value || "");
          if (!traceId) return <Typography variant="caption">-</Typography>;
          return (
            <Button
              size="small"
              variant="outlined"
              component={RouterLink}
              to={`/console/audit/transcript-replay/${encodeURIComponent(traceId)}`}
            >
              查看 trace
            </Button>
          );
        },
      },
    ],
    [],
  );

  return (
    <Stack spacing={2} data-testid="reflection-daily-page">
      <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
        <Box>
          <Typography variant="h5">插件与系统反思日视图</Typography>
          <Typography variant="body2" color="text.secondary">
            这里按日期从反思数据库分页读取真实记录，用于查看这一天插件、九问、学习和维护流程到底产生了哪些反思。
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<Play size={16} />}
          disabled={maintenanceLoading}
          onClick={() => void forceAutoOrganize()}
        >
          {maintenanceLoading ? "启动中..." : "强制启动自动整理"}
        </Button>
      </Stack>

      <Paper sx={{ p: 2 }}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems={{ xs: "stretch", md: "center" }}>
          <TextField
            label="日期"
            type="date"
            value={date}
            onChange={(event) => {
              setDate(event.target.value);
              setPaginationModel((current) => ({ ...current, page: 0 }));
            }}
            InputLabelProps={{ shrink: true }}
            sx={{ width: { xs: "100%", md: 200 } }}
          />
          <FormControl sx={{ minWidth: 220 }}>
            <InputLabel id="reflection-source-filter-label">来源范围</InputLabel>
            <Select
              labelId="reflection-source-filter-label"
              label="来源范围"
              value={source}
              onChange={(event) => {
                setSource(event.target.value as SourceFilter);
                setPaginationModel((current) => ({ ...current, page: 0 }));
              }}
            >
              <MenuItem value="all">全部反思</MenuItem>
              <MenuItem value="plugin">插件反思</MenuItem>
              <MenuItem value="nine_questions">九问反思</MenuItem>
            </Select>
          </FormControl>
          <Button variant="contained" onClick={() => void load()}>
            刷新
          </Button>
          <Chip label={`当天记录: ${rowCount}`} color="primary" variant="outlined" />
          {databaseBacked ? <Chip label="数据库分页" color="success" variant="outlined" /> : null}
        </Stack>
      </Paper>

      {error ? <Alert severity="error">{error}</Alert> : null}

      {lastMaintenance ? (
        <Alert severity="success" variant="outlined">
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
            <Typography variant="body2">{lastMaintenance.summary}</Typography>
            <Chip size="small" label={`trace=${lastMaintenance.trace_id}`} />
            <Chip size="small" label={`memory=${lastMaintenance.used_memory_count}`} />
            <Chip size="small" label={`deleted=${lastMaintenance.deleted_reflection_count}`} />
            <Chip
              size="small"
              label={`reflection=${lastMaintenance.generated_reflection_id}`}
              component={RouterLink}
              to={`/console/audit/transcript-replay/${encodeURIComponent(lastMaintenance.trace_id)}`}
              clickable
            />
          </Stack>
        </Alert>
      ) : null}

      <Box sx={{ height: 620, width: "100%" }}>
        <DataGrid
          getRowId={(row) => row.reflection_id}
          rows={rows}
          columns={columns}
          pageSizeOptions={[25, 50, 100]}
          paginationMode="server"
          paginationModel={paginationModel}
          onPaginationModelChange={setPaginationModel}
          rowCount={rowCount}
          loading={loading}
          disableRowSelectionOnClick
        />
      </Box>
    </Stack>
  );
}
