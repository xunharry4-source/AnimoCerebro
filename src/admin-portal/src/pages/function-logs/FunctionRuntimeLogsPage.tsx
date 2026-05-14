import { useCallback, useEffect, useMemo, useState } from "react";
import { Link as RouterLink, useLocation } from "react-router-dom";
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
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import RefreshIcon from "@mui/icons-material/Refresh";
import ArticleIcon from "@mui/icons-material/Article";

type LogEntry = {
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

type LogResponse = {
  items: LogEntry[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
};

type LogKind = "core" | "cli" | "agent" | "mcp" | "external-connectors" | "plugins";

type KindConfig = {
  title: string;
  subtitle: string;
  sourceModule?: string;
  sourceModules?: string[];
  backTo: string;
  functionLabel: string;
};

const KIND_CONFIG: Record<LogKind, KindConfig> = {
  core: {
    title: "核心功能运行日志",
    subtitle: "按核心模块与功能动作查看任务、九问、学习、反思、记忆、模拟、升级和审计运行日志。",
    sourceModules: ["core", "kernel", "nine_questions", "task", "learning", "reflection", "memory", "simulation", "upgrade", "audit"],
    backTo: "/console/dashboard",
    functionLabel: "核心功能",
  },
  cli: {
    title: "CLI 功能运行日志",
    subtitle: "按 CLI command/function 查看真实运行、测试调用和管理审计日志。",
    sourceModule: "cli",
    backTo: "/console/cli-tools",
    functionLabel: "CLI 功能",
  },
  agent: {
    title: "Agent 功能运行日志",
    subtitle: "按 Agent 与 invocation/capability 查看派发、回执和执行日志。",
    sourceModule: "agent",
    backTo: "/console/agents",
    functionLabel: "Agent 功能",
  },
  mcp: {
    title: "MCP Tool 运行日志",
    subtitle: "按 MCP server.tool 查看工具调用和服务管理日志。",
    sourceModule: "mcp",
    backTo: "/console/mcp-servers",
    functionLabel: "MCP Tool",
  },
  "external-connectors": {
    title: "外接连接器功能运行日志",
    subtitle: "按 connector.capability 查看外接应用真实调用、证据和失败信息。",
    sourceModule: "connector",
    backTo: "/console/external-connectors",
    functionLabel: "外接功能",
  },
  plugins: {
    title: "内部插件功能运行日志",
    subtitle: "按内部插件 tool/function 查看启停、绑定、测试和运行日志。",
    sourceModule: "plugin",
    backTo: "/console/plugins",
    functionLabel: "内部插件功能",
  },
};

const STATUS_OPTIONS = ["all", "success", "failed", "completed", "active", "degraded", "rejected", "skipped"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function nestedDetails(entry: LogEntry): Record<string, unknown> {
  const nested = entry.details?.details;
  return isRecord(nested) ? nested : entry.details || {};
}

function text(value: unknown): string {
  return String(value ?? "").trim();
}

function firstText(...values: unknown[]): string {
  for (const value of values) {
    const item = text(value);
    if (item) return item;
  }
  return "";
}

function functionKey(entry: LogEntry, kind: LogKind): string {
  const details = nestedDetails(entry);
  if (kind === "core") {
    const module = firstText(entry.source_module, details.source_module, "core");
    const capability = firstText(details.function_name, details.service_method, details.capability, details.task_type, details.workflow, entry.action, entry.object_id);
    return capability ? `${module}.${capability}` : module || "unknown-core-function";
  }
  if (kind === "mcp") {
    const server = firstText(details.server_id, entry.object_id);
    const tool = firstText(details.tool_name, details.tool, details.capability);
    return tool ? `${server}.${tool}` : server || "unknown-mcp-tool";
  }
  if (kind === "external-connectors") {
    const connector = firstText(details.connector_id, entry.object_id);
    const capability = firstText(details.capability, details.capability_name);
    return capability ? `${connector}.${capability}` : connector || "unknown-connector-capability";
  }
  if (kind === "cli") {
    return firstText(details.command_name, details.tool_name, details.command, entry.object_id, entry.object_label) || "unknown-cli-command";
  }
  if (kind === "agent") {
    const agent = firstText(details.agent_id, entry.object_id);
    const capability = firstText(details.capability, details.external_task_ref, details.task_ref);
    return capability ? `${agent}.${capability}` : agent || "unknown-agent-function";
  }
  const plugin = firstText(details.plugin_id, details.tool_id, details.cognitive_plugin_id, details.functional_plugin_id, entry.object_id);
  const capability = firstText(details.function_name, details.capability, details.functional_plugin_id);
  return capability && capability !== plugin ? `${plugin}.${capability}` : plugin || "unknown-plugin-function";
}

function formatTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function compactDetails(entry: LogEntry): string {
  const details = nestedDetails(entry);
  const preferred = [
    "trace_id",
    "capability",
    "tool_name",
    "command_name",
    "server_id",
    "connector_id",
    "agent_id",
    "plugin_id",
    "task_id",
    "external_task_ref",
    "evidence_validation_status",
    "error_code",
    "error_stage",
  ];
  const parts = preferred
    .filter((key) => details[key] !== undefined && details[key] !== null && details[key] !== "")
    .map((key) => `${key}: ${formatValue(details[key])}`);
  return parts.length ? parts.join(" · ") : JSON.stringify(details);
}

export default function FunctionRuntimeLogsPage() {
  const location = useLocation();
  const pathname = location.pathname;
  const kind: LogKind = pathname.includes("/core/")
    ? "core"
    : pathname.includes("/agents/")
    ? "agent"
    : pathname.includes("/mcp-servers/")
      ? "mcp"
      : pathname.includes("/external-connectors/")
        ? "external-connectors"
        : pathname.includes("/plugins/")
          ? "plugins"
          : "cli";
  const config = KIND_CONFIG[kind];
  const [rows, setRows] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");
  const [selectedFunction, setSelectedFunction] = useState("all");
  const functionKeyParam = new URLSearchParams(location.search).get("function_key")?.trim() || "";
  const functionPrefixParam = new URLSearchParams(location.search).get("function_prefix")?.trim() || "";

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const sourceModules = config.sourceModules ?? (config.sourceModule ? [config.sourceModule] : []);
      const pages = await Promise.all(
        sourceModules.map(async (sourceModule) => {
          const params = new URLSearchParams({
            source_module: sourceModule,
            page: "1",
            page_size: "200",
          });
          if (status !== "all") params.set("status", status);
          if (search.trim()) params.set("search", search.trim());
          const response = await fetch(`/api/web/module-logs?${params.toString()}`);
          const payload = (await response.json()) as LogResponse | { detail?: unknown };
          if (!response.ok) {
            const detail = (payload as { detail?: unknown }).detail;
            throw new Error(typeof detail === "string" ? detail : `日志查询失败: ${sourceModule} HTTP ${response.status}`);
          }
          return (payload as LogResponse).items || [];
        })
      );
      setRows(pages.flat().sort((a, b) => b.timestamp.localeCompare(a.timestamp) || b.log_id.localeCompare(a.log_id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "日志查询失败");
    } finally {
      setLoading(false);
    }
  }, [config.sourceModule, config.sourceModules, search, status]);

  useEffect(() => {
    setSelectedFunction(functionKeyParam || functionPrefixParam || "all");
    void fetchLogs();
  }, [fetchLogs, functionKeyParam, functionPrefixParam, kind]);

  const functionRows = useMemo(() => {
    const grouped = new Map<string, { id: string; function_key: string; latest_status: string; latest_at: string; count: number; failures: number }>();
    for (const entry of rows) {
      const key = functionKey(entry, kind);
      const current = grouped.get(key);
      const failed = entry.status === "failed" || entry.status === "rejected";
      if (!current) {
        grouped.set(key, {
          id: key,
          function_key: key,
          latest_status: entry.status,
          latest_at: entry.timestamp,
          count: 1,
          failures: failed ? 1 : 0,
        });
        continue;
      }
      current.count += 1;
      current.failures += failed ? 1 : 0;
      if (entry.timestamp > current.latest_at) {
        current.latest_at = entry.timestamp;
        current.latest_status = entry.status;
      }
    }
    return Array.from(grouped.values()).sort((a, b) => b.latest_at.localeCompare(a.latest_at));
  }, [kind, rows]);

  const filteredLogs = useMemo(() => {
    if (selectedFunction === "all") return rows;
    return rows.filter((entry) => {
      const key = functionKey(entry, kind);
      if (functionPrefixParam && selectedFunction === functionPrefixParam) {
        return key === functionPrefixParam || key.startsWith(`${functionPrefixParam}.`);
      }
      return key === selectedFunction;
    });
  }, [functionPrefixParam, kind, rows, selectedFunction]);

  const summaryColumns: GridColDef[] = [
    {
      field: "function_key",
      headerName: config.functionLabel,
      minWidth: 260,
      flex: 1,
      renderCell: (params) => (
        <Tooltip title={String(params.value || "-")} placement="top-start">
          <Typography variant="body2" sx={{ overflow: "hidden", textOverflow: "ellipsis" }}>
            {String(params.value || "-")}
          </Typography>
        </Tooltip>
      ),
    },
    { field: "latest_status", headerName: "最新状态", width: 130, renderCell: (params) => <Chip size="small" variant="outlined" label={String(params.value || "-")} /> },
    { field: "count", headerName: "日志数", width: 100 },
    { field: "failures", headerName: "失败数", width: 100 },
    { field: "latest_at", headerName: "最新时间", width: 190, valueGetter: (_value, row) => formatTime(row.latest_at) },
  ];

  const logColumns: GridColDef[] = [
    { field: "timestamp", headerName: "时间", width: 190, valueGetter: (_value, row: LogEntry) => formatTime(row.timestamp) },
    { field: "function_key", headerName: config.functionLabel, minWidth: 240, valueGetter: (_value, row: LogEntry) => functionKey(row, kind) },
    { field: "action", headerName: "动作", width: 160, valueGetter: (_value, row: LogEntry) => row.action_label || row.action },
    { field: "status", headerName: "状态", width: 130, renderCell: (params) => <Chip size="small" variant="outlined" label={String(params.value || "-")} /> },
    {
      field: "content",
      headerName: "内容",
      minWidth: 360,
      flex: 1,
      renderCell: (params) => (
        <Tooltip title={String(params.value || "-")} placement="top-start">
          <Typography variant="body2" sx={{ overflow: "hidden", textOverflow: "ellipsis" }}>
            {String(params.value || "-")}
          </Typography>
        </Tooltip>
      ),
    },
    {
      field: "details",
      headerName: "运行细节",
      minWidth: 360,
      flex: 0.9,
      valueGetter: (_value, row: LogEntry) => compactDetails(row),
      renderCell: (params) => (
        <Tooltip title={String(params.value || "-")} placement="top-start">
          <Typography variant="body2" sx={{ overflow: "hidden", textOverflow: "ellipsis" }}>
            {String(params.value || "-")}
          </Typography>
        </Tooltip>
      ),
    },
  ];

  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={3}>
        <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
          <Stack direction="row" spacing={2} alignItems="center">
            <Button component={RouterLink} to={config.backTo} startIcon={<ArrowBackIcon />} variant="outlined">
              返回
            </Button>
            <Box>
              <Typography variant="h4" component="h1" sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <ArticleIcon color="primary" />
                {config.title}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {config.subtitle}
              </Typography>
              {config.sourceModules ? (
                <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap" sx={{ mt: 1 }}>
                  {config.sourceModules.map((sourceModule) => (
                    <Chip key={sourceModule} size="small" label={sourceModule} variant="outlined" />
                  ))}
                </Stack>
              ) : null}
            </Box>
          </Stack>
          <Button startIcon={<RefreshIcon />} variant="outlined" onClick={() => void fetchLogs()} disabled={loading}>
            {loading ? "刷新中" : "刷新"}
          </Button>
        </Stack>

        <Card variant="outlined">
          <CardContent>
            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
              <TextField
                label="搜索日志"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void fetchLogs();
                }}
                fullWidth
                size="small"
              />
              <FormControl size="small" sx={{ minWidth: 180 }}>
                <InputLabel id="function-log-status-label">状态</InputLabel>
                <Select labelId="function-log-status-label" label="状态" value={status} onChange={(event) => setStatus(String(event.target.value))}>
                  {STATUS_OPTIONS.map((item) => (
                    <MenuItem key={item} value={item}>
                      {item === "all" ? "全部" : item}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <Button variant="contained" onClick={() => void fetchLogs()}>
                查询
              </Button>
            </Stack>
          </CardContent>
        </Card>

        {error ? <Alert severity="error">{error}</Alert> : null}

        <Card>
          <CardContent>
            <Stack spacing={2}>
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Typography variant="h6">功能列表</Typography>
                <Chip label={`${functionRows.length} 个功能`} variant="outlined" />
              </Stack>
              <Box sx={{ height: 300, width: "100%" }}>
                <DataGrid
                  rows={functionRows}
                  columns={summaryColumns}
                  loading={loading}
                  disableRowSelectionOnClick
                  onRowClick={(params) => setSelectedFunction(String(params.row.function_key))}
                  pageSizeOptions={[5, 10, 25]}
                  initialState={{ pagination: { paginationModel: { pageSize: 5, page: 0 } } }}
                  localeText={{ noRowsLabel: "没有功能运行日志" }}
                  sx={{ "& .MuiDataGrid-row": { cursor: "pointer" } }}
                />
              </Box>
            </Stack>
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <Stack spacing={2}>
              <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
                <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
                  <Typography variant="h6">运行日志</Typography>
                  <Chip label={selectedFunction === "all" ? "全部功能" : selectedFunction} color={selectedFunction === "all" ? "default" : "primary"} variant="outlined" />
                </Stack>
                {selectedFunction !== "all" ? (
                  <Button size="small" variant="outlined" onClick={() => setSelectedFunction("all")}>
                    显示全部
                  </Button>
                ) : null}
              </Stack>
              <Box sx={{ height: 560, width: "100%" }}>
                <DataGrid
                  rows={filteredLogs}
                  columns={logColumns}
                  getRowId={(row) => row.log_id}
                  loading={loading}
                  disableRowSelectionOnClick
                  pageSizeOptions={[10, 25, 50]}
                  initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } } }}
                  localeText={{ noRowsLabel: "没有运行日志" }}
                />
              </Box>
            </Stack>
          </CardContent>
        </Card>
      </Stack>
    </Box>
  );
}
