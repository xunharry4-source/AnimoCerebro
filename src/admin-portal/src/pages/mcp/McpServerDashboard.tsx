import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Drawer,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { DataGrid, GridColDef } from "@mui/x-data-grid";
import AddIcon from "@mui/icons-material/Add";
import { Link as RouterLink, useNavigate } from "react-router-dom";

type McpToolItem = {
  tool_name: string;
  description: string;
  mapped_domain: "cognitive" | "execution";
  plugin_id: string;
  feature_code: string;
  execution_domain?: string | null;
  read_only: boolean;
  side_effect_free: boolean;
  mutates_state: boolean;
  requires_cloud_audit: boolean;
  status: string;
};

type McpServerItem = {
  server_id: string;
  transport_type: string;
  status: "online" | "offline" | "degraded";
  tool_count: number;
  error_message?: string | null;
  tools: McpToolItem[];
};

function getHealthColor(status: McpServerItem["status"]): "success" | "default" | "warning" {
  switch (status) {
    case "online":
      return "success";
    case "degraded":
      return "warning";
    default:
      return "default";
  }
}

import { Locale, mcpServerCopy } from "../../i18n";

export default function McpServerDashboard() {
  const navigate = useNavigate();
  const locale: Locale = "zh-CN";
  const copy = mcpServerCopy[locale];
  const [rows, setRows] = useState<McpServerItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedServer, setSelectedServer] = useState<McpServerItem | null>(null);
  const [selectedToolName, setSelectedToolName] = useState<string>("");
  const [openRegister, setOpenRegister] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [registerData, setRegisterData] = useState({
    server_id: "",
    transport_type: "stdio",
    command: "",
    args: "",
  });
  const [testData, setTestData] = useState({
    tool_name: "",
    arguments_json: "{\"query\":\"runbook\"}",
  });

  useEffect(() => {
    void loadServers();
  }, []);

  const loadServers = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/web/mcp-servers");
      if (!response.ok) {
        throw new Error(`${copy.fetchServersFailed}（HTTP ${response.status}）`);
      }
      const payload = (await response.json()) as McpServerItem[];
      setRows(payload);
    } catch (err: any) {
      setError(err?.message || copy.fetchServersFailed);
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async () => {
    try {
      const response = await fetch("/api/web/mcp-servers/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          server_id: registerData.server_id,
          transport_type: registerData.transport_type,
          command: registerData.command,
          args: registerData.args.split(" ").map((item) => item.trim()).filter(Boolean),
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.detail || copy.registerFailed);
      }
      setOpenRegister(false);
      setRegisterData({ server_id: "", transport_type: "stdio", command: "", args: "" });
      void loadServers();
    } catch (err: any) {
      setError(err?.message || copy.registerFailed);
    }
  };

  const handleTestCall = async () => {
    if (!selectedServer || !testData.tool_name) return;
    setTestResult(null);
    try {
      const response = await fetch(`/api/web/mcp-servers/${selectedServer.server_id}/test-call`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tool_name: testData.tool_name,
          arguments: JSON.parse(testData.arguments_json || "{}"),
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.detail || copy.testCallFailed);
      }
      setTestResult(JSON.stringify(payload, null, 2));
    } catch (err: any) {
      setTestResult(err?.message || copy.testCallFailed);
    }
  };

  const columns: GridColDef[] = [
    { field: "server_id", headerName: copy.serverName, flex: 1.1, minWidth: 200 },
    { field: "transport_type", headerName: copy.connectionType, flex: 0.7, minWidth: 120 },
    { field: "tool_count", headerName: copy.toolCount, flex: 0.7, minWidth: 120 },
    {
      field: "status",
      headerName: copy.healthStatus,
      flex: 0.9,
      minWidth: 160,
      renderCell: (params) => <Chip label={params.value} color={getHealthColor(params.value)} size="small" />,
    },
  ];

  if (loading) {
    return <CircularProgress />;
  }

  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={3}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Box>
          <Typography variant="h4" gutterBottom>
            {copy.title}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {copy.subtitle}
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setOpenRegister(true)}>
          {copy.registerServer}
        </Button>
      </Stack>

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      ) : null}

      <DataGrid
        autoHeight
        disableRowSelectionOnClick
        disableVirtualization
        rows={rows.map((item) => ({ id: item.server_id, ...item }))}
        columns={columns}
        pageSizeOptions={[10]}
        initialState={{
          pagination: { paginationModel: { page: 0, pageSize: 10 } },
        }}
        onRowClick={(params) => setSelectedServer(params.row as McpServerItem)}
        sx={{ backgroundColor: "background.paper", "& .MuiDataGrid-row": { cursor: "pointer" } }}
      />

      <Drawer
        anchor="right"
        open={Boolean(selectedServer)}
        onClose={() => setSelectedServer(null)}
        PaperProps={{ sx: { width: 460, p: 3 } }}
      >
        {selectedServer ? (
          <Stack spacing={2}>
            <Box>
              <Typography variant="h5">{selectedServer.server_id}</Typography>
              <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                <Chip label={selectedServer.transport_type} variant="outlined" />
                <Chip label={selectedServer.status} color={getHealthColor(selectedServer.status)} />
                <Chip label={`${selectedServer.tool_count} tools`} variant="outlined" />
              </Stack>
              <Button
                sx={{ mt: 1 }}
                size="small"
                variant="outlined"
                onClick={() => navigate(`/console/mcp-servers/${selectedServer.server_id}`)}
              >
                进入服务详情页
              </Button>
            </Box>
            {selectedServer.error_message ? <Alert severity="warning">{selectedServer.error_message}</Alert> : null}
            <Divider />
            <Typography variant="h6">{copy.toolList}</Typography>
            {selectedServer.tools.map((tool) => (
              <Box key={tool.plugin_id} sx={{ p: 2, border: "1px solid", borderColor: "divider", borderRadius: 2 }}>
                <Stack direction="row" spacing={1} sx={{ mb: 1 }} useFlexGap flexWrap="wrap">
                  <Chip
                    label={tool.mapped_domain === "cognitive" ? copy.cognitiveAssist : copy.physicalExecution}
                    color={tool.mapped_domain === "cognitive" ? "primary" : "error"}
                    size="small"
                  />
                  {tool.execution_domain ? <Chip label={tool.execution_domain} variant="outlined" size="small" /> : null}
                  {tool.requires_cloud_audit ? <Chip label="CloudAudit" color="warning" size="small" /> : null}
                </Stack>
                <Typography variant="subtitle2">{tool.tool_name}</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  {tool.description}
                </Typography>
                <Typography variant="caption" display="block">
                  plugin_id: {tool.plugin_id}
                </Typography>
                <Typography variant="caption" display="block">
                  feature_code: {tool.feature_code}
                </Typography>
                <Button
                  sx={{ mt: 1 }}
                  size="small"
                  variant="outlined"
                  onClick={() => {
                    setSelectedToolName(tool.tool_name);
                    setTestData((current) => ({ ...current, tool_name: tool.tool_name }));
                  }}
                >
                  {copy.selectForTest}
                </Button>
              </Box>
            ))}
            <Divider />
            <Typography variant="h6">{copy.testCall}</Typography>
            <TextField
              label={copy.toolName}
              fullWidth
              value={testData.tool_name}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setTestData({ ...testData, tool_name: e.target.value })
              }
              helperText={selectedToolName ? `${copy.selectedToolHint}${selectedToolName}` : copy.toolName}
            />
            <TextField
              label={copy.paramsJson}
              fullWidth
              multiline
              rows={4}
              value={testData.arguments_json}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setTestData({ ...testData, arguments_json: e.target.value })
              }
            />
            <Button variant="contained" onClick={() => void handleTestCall()} disabled={!testData.tool_name}>
              {copy.executeTest}
            </Button>
            {testResult ? (
              <Alert severity="info">
                <Stack spacing={1}>
                  <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{testResult}</pre>
                  {(() => {
                    try {
                      const parsed = JSON.parse(testResult);
                      const traceId = String(parsed?.trace_id || "");
                      if (!traceId) {
                        return null;
                      }
                      return (
                        <Button
                          size="small"
                          variant="outlined"
                          component={RouterLink}
                          to={`/console/audit/transcript-replay/${encodeURIComponent(traceId)}`}
                          sx={{ alignSelf: "flex-start" }}
                        >
                          查看 trace 回放
                        </Button>
                      );
                    } catch {
                      return null;
                    }
                  })()}
                </Stack>
              </Alert>
            ) : null}
          </Stack>
        ) : null}
      </Drawer>

      <Dialog open={openRegister} onClose={() => setOpenRegister(false)} fullWidth maxWidth="sm">
        <DialogTitle>{copy.registerDialogTitle}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={copy.serverId}
              fullWidth
              value={registerData.server_id}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setRegisterData({ ...registerData, server_id: e.target.value })
              }
            />
            <TextField
              label={copy.transport}
              fullWidth
              value={registerData.transport_type}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setRegisterData({ ...registerData, transport_type: e.target.value })
              }
            />
            <TextField
              label={copy.commandUrl}
              fullWidth
              value={registerData.command}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setRegisterData({ ...registerData, command: e.target.value })
              }
            />
            <TextField
              label={copy.argsSpaceSeparated}
              fullWidth
              value={registerData.args}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setRegisterData({ ...registerData, args: e.target.value })
              }
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenRegister(false)}>{copy.cancel}</Button>
          <Button
            variant="contained"
            onClick={() => void handleRegister()}
            disabled={!registerData.server_id || !registerData.command}
          >
            {copy.confirmRegister}
          </Button>
        </DialogActions>
      </Dialog>
      </Stack>
    </Box>
  );
}
