import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link as RouterLink, useParams, useSearchParams } from "react-router-dom";
import {
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
  Tooltip,
  Typography,
} from "@mui/material";
import { DataGrid, GridColDef } from "@mui/x-data-grid";
import ArticleIcon from "@mui/icons-material/Article";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import RefreshIcon from "@mui/icons-material/Refresh";

type ModuleLogEntry = {
  log_id: string;
  timestamp: string;
  source_module: string;
  object_id: string;
  object_label: string;
  action: string;
  action_label: string;
  source: string;
  content: string;
  status: string;
  operator_id: string;
  details: Record<string, unknown>;
};

type ModuleLogResponse = {
  items: ModuleLogEntry[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
};

const MODULES: Record<string, { titleKey: string; source: string; backTo: string }> = {
  "": { titleKey: "moduleLogs.modules.all", source: "", backTo: "/console/dashboard" },
  agents: { titleKey: "moduleLogs.modules.agents", source: "agent", backTo: "/console/agents" },
  plugins: { titleKey: "moduleLogs.modules.plugins", source: "plugin", backTo: "/console/plugins" },
  upgrades: { titleKey: "moduleLogs.modules.upgrades", source: "upgrade", backTo: "/console/upgrades" },
  "cli-tools": { titleKey: "moduleLogs.modules.cliTools", source: "cli", backTo: "/console/cli-tools" },
  "mcp-servers": { titleKey: "moduleLogs.modules.mcpServers", source: "mcp", backTo: "/console/mcp-servers" },
  tasks: { titleKey: "moduleLogs.modules.tasks", source: "task", backTo: "/console/tasks" },
  "external-connectors": {
    titleKey: "moduleLogs.modules.externalConnectors",
    source: "connector",
    backTo: "/console/external-connectors",
  },
  learning: { titleKey: "moduleLogs.modules.learning", source: "learning", backTo: "/console/learning" },
  reflections: { titleKey: "moduleLogs.modules.reflections", source: "reflection", backTo: "/console/reflections" },
  memory: { titleKey: "moduleLogs.modules.memory", source: "memory", backTo: "/console/memory" },
  simulation: { titleKey: "moduleLogs.modules.simulation", source: "simulation", backTo: "/console/simulation" },
};

function formatTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

const DETAIL_LABELS: Record<string, string> = {
  server_id: "server_id",
  transport_type: "transport",
  command: "command",
  args: "args",
  scope: "scope",
  auth_type: "auth",
  credential_ref: "credential_ref",
  help_doc_url: "help_doc_url",
  project_doc_url: "project_doc_url",
  documentation_learning_required: "doc_learning",
  tool_bindings: "tool_bindings",
  tool_count: "tool_count",
  status: "status",
  error: "error",
};

function formatDetailValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string" || typeof value === "number") return String(value);
  return JSON.stringify(value);
}

function formatLogDetails(details: Record<string, unknown>): string {
  const nestedDetails = details.details;
  const displayDetails = isRecord(nestedDetails) && Object.keys(nestedDetails).length > 0 ? nestedDetails : details;
  const entries = Object.entries(displayDetails).filter(([, value]) => {
    if (value === null || value === undefined || value === "") return false;
    if (Array.isArray(value)) return value.length > 0;
    if (isRecord(value)) return Object.keys(value).length > 0;
    return true;
  });
  if (!entries.length) return "-";
  return entries.map(([key, value]) => `${DETAIL_LABELS[key] || key}: ${formatDetailValue(value)}`).join(" · ");
}

export default function ModuleLogsPage() {
  const { t } = useTranslation();
  const { moduleId = "" } = useParams<{ moduleId: string }>();
  const [searchParams] = useSearchParams();
  const moduleConfig = MODULES[moduleId] || {
    titleKey: "",
    source: moduleId,
    backTo: "/console/dashboard",
  };
  const title = moduleConfig.titleKey
    ? t(moduleConfig.titleKey)
    : t("moduleLogs.modules.unknown", { module: moduleId || t("moduleLogs.unknownModule") });
  const sourceModule = searchParams.get("source_module") || moduleConfig.source;

  const [rows, setRows] = useState<ModuleLogEntry[]>([]);
  const [rowCount, setRowCount] = useState(0);
  const [paginationModel, setPaginationModel] = useState({ page: 0, pageSize: 25 });
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set("page", String(paginationModel.page + 1));
      params.set("page_size", String(paginationModel.pageSize));
      if (sourceModule) params.set("source_module", sourceModule);
      if (appliedSearch.trim()) params.set("search", appliedSearch.trim());
      if (status !== "all") params.set("status", status);
      const response = await fetch(`/api/web/module-logs?${params.toString()}`);
      const payload = (await response.json()) as ModuleLogResponse | { detail?: unknown };
      if (!response.ok) {
        throw new Error(
          typeof (payload as any)?.detail === "string"
            ? (payload as any).detail
            : t("moduleLogs.fetchFailedWithStatus", { status: response.status }),
        );
      }
      const pagePayload = payload as ModuleLogResponse;
      setRows(pagePayload.items || []);
      setRowCount(pagePayload.total_items || 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("moduleLogs.fetchFailed"));
    } finally {
      setLoading(false);
    }
  }, [appliedSearch, paginationModel.page, paginationModel.pageSize, sourceModule, status, t]);

  useEffect(() => {
    void fetchLogs();
  }, [fetchLogs]);

  const columns: GridColDef[] = useMemo(() => [
    {
      field: "timestamp",
      headerName: t("moduleLogs.time"),
      width: 190,
      valueGetter: (_value, row: ModuleLogEntry) => formatTime(row.timestamp),
    },
    {
      field: "content",
      headerName: t("moduleLogs.content"),
      minWidth: 420,
      flex: 1,
      valueGetter: (_value, row: ModuleLogEntry) => row.content || "-",
      renderCell: (params) => (
        <Tooltip title={String(params.value || "-")} placement="top-start">
          <Typography variant="body2" sx={{ overflow: "hidden", textOverflow: "ellipsis", fontWeight: 500 }}>
            {String(params.value || "-")}
          </Typography>
        </Tooltip>
      ),
    },
    {
      field: "action",
      headerName: t("moduleLogs.action"),
      width: 150,
      valueGetter: (_value, row: ModuleLogEntry) => row.action_label || row.action || "-",
    },
    {
      field: "status",
      headerName: t("moduleLogs.status"),
      width: 160,
      valueGetter: (_value, row: ModuleLogEntry) => row.status || "-",
      renderCell: (params) => <Chip size="small" variant="outlined" label={String(params.value || "-")} />,
    },
    { field: "source", headerName: t("moduleLogs.source"), width: 220 },
    { field: "object_id", headerName: t("moduleLogs.objectId"), width: 220 },
    {
      field: "details",
      headerName: t("moduleLogs.details"),
      minWidth: 320,
      flex: 0.8,
      valueGetter: (_value, row: ModuleLogEntry) => formatLogDetails(row.details || {}),
      renderCell: (params) => (
        <Tooltip title={String(params.value || "-")} placement="top-start">
          <Typography variant="body2" sx={{ overflow: "hidden", textOverflow: "ellipsis" }}>
            {String(params.value || "-")}
          </Typography>
        </Tooltip>
      ),
    },
  ], [t]);

  const applySearch = () => {
    setPaginationModel((current) => ({ ...current, page: 0 }));
    setAppliedSearch(search);
  };

  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={3}>
        <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
          <Stack direction="row" spacing={2} alignItems="center">
            <Button component={RouterLink} to={moduleConfig.backTo} startIcon={<ArrowBackIcon />} variant="outlined">
              {t("common.back")}
            </Button>
            <Box>
              <Typography variant="h4" component="h1" sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <ArticleIcon color="primary" />
                {title}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t("moduleLogs.subtitle", { module: sourceModule || moduleId })}
              </Typography>
            </Box>
          </Stack>
          <Button startIcon={<RefreshIcon />} variant="outlined" onClick={() => void fetchLogs()} disabled={loading}>
            {loading ? t("common.refreshing") : t("common.refresh")}
          </Button>
        </Stack>

        <Card variant="outlined">
          <CardContent>
            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
              <TextField
                label={t("moduleLogs.search")}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") applySearch();
                }}
                fullWidth
                size="small"
              />
              <FormControl size="small" sx={{ minWidth: 180 }}>
                <InputLabel id="module-log-status-label">{t("moduleLogs.status")}</InputLabel>
                <Select
                  labelId="module-log-status-label"
                  label={t("moduleLogs.status")}
                  value={status}
                  onChange={(event) => {
                    setStatus(String(event.target.value));
                    setPaginationModel((current) => ({ ...current, page: 0 }));
                  }}
                >
                  <MenuItem value="all">{t("common.all")}</MenuItem>
                  <MenuItem value="completed">completed</MenuItem>
                  <MenuItem value="failed">failed</MenuItem>
                  <MenuItem value="skipped">skipped</MenuItem>
                  <MenuItem value="active">active</MenuItem>
                  <MenuItem value="degraded">degraded</MenuItem>
                  <MenuItem value="rejected">rejected</MenuItem>
                </Select>
              </FormControl>
              <Button variant="contained" onClick={applySearch}>
                {t("common.search")}
              </Button>
            </Stack>
          </CardContent>
        </Card>

        {error ? <Alert severity="error">{error}</Alert> : null}

        <Card>
          <CardContent>
            <Box sx={{ height: 640, width: "100%" }}>
              <DataGrid
                rows={rows}
                columns={columns}
                getRowId={(row) => row.log_id}
                loading={loading}
                pageSizeOptions={[10, 25, 50, 100]}
                paginationMode="server"
                paginationModel={paginationModel}
                onPaginationModelChange={setPaginationModel}
                rowCount={rowCount}
                disableRowSelectionOnClick
                localeText={{ noRowsLabel: t("moduleLogs.noData") }}
              />
            </Box>
          </CardContent>
        </Card>
      </Stack>
    </Box>
  );
}
