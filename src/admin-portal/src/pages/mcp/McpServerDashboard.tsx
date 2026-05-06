import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
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
  FormControl,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { DataGrid, GridColDef } from "@mui/x-data-grid";
import AddIcon from "@mui/icons-material/Add";
import PowerSettingsNewIcon from "@mui/icons-material/PowerSettingsNew";
import BlockIcon from "@mui/icons-material/Block";
import ArticleIcon from "@mui/icons-material/Article";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import { Trash2 } from "lucide-react";

type McpToolItem = {
  tool_name: string;
  description: string;
  mapped_domain: "cognitive" | "execution";
  mcp_id: string;
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
  help_doc_url?: string | null;
  project_doc_url?: string | null;
  tools: McpToolItem[];
};

type McpRegistrationExample = {
  key: string;
  title: string;
  summary: string;
  values: {
    server_id: string;
    transport_type: string;
    command: string;
    args: string;
    help_doc_url: string;
    project_doc_url: string;
    auth_type: string;
    env_name: string;
    header_name: string;
  };
};

type McpRegisterFormData = {
  server_id: string;
  transport_type: string;
  command: string;
  args: string;
  help_doc_url: string;
  project_doc_url: string;
  auth_type: string;
  credential_id: string;
  api_key: string;
  env_name: string;
  header_name: string;
  credential_payload_json: string;
  login_http_url: string;
  login_http_path: string;
  login_http_method: string;
  login_http_body_json: string;
  access_token_path: string;
};

const MCP_REGISTRATION_EXAMPLES: McpRegistrationExample[] = [
  {
    key: "notion",
    title: "Notion MCP",
    summary: "stdio / npx / API Token",
    values: {
      server_id: "notion",
      transport_type: "stdio",
      command: "npx",
      args: "-y @notionhq/notion-mcp-server",
      help_doc_url: "https://github.com/makenotion/notion-mcp-server",
      project_doc_url: "",
      auth_type: "api_key",
      env_name: "NOTION_TOKEN",
      header_name: "",
    },
  },
  {
    key: "filesystem",
    title: "Filesystem MCP",
    summary: "stdio / npx / local project path",
    values: {
      server_id: "filesystem",
      transport_type: "stdio",
      command: "npx",
      args: "-y @modelcontextprotocol/server-filesystem <project-path>",
      help_doc_url: "https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem",
      project_doc_url: "",
      auth_type: "none",
      env_name: "",
      header_name: "",
    },
  },
  {
    key: "github",
    title: "GitHub MCP",
    summary: "streamable_http / URL / bearer token",
    values: {
      server_id: "github",
      transport_type: "streamable_http",
      command: "https://api.githubcopilot.com/mcp/",
      args: "",
      help_doc_url: "https://github.com/github/github-mcp-server",
      project_doc_url: "",
      auth_type: "api_key",
      env_name: "",
      header_name: "Authorization",
    },
  },
];

const INITIAL_MCP_REGISTER_DATA: McpRegisterFormData = {
  server_id: "",
  transport_type: "stdio",
  command: "",
  args: "",
  help_doc_url: "",
  project_doc_url: "",
  auth_type: "none",
  credential_id: "",
  api_key: "",
  env_name: "",
  header_name: "",
  credential_payload_json: "{}",
  login_http_url: "",
  login_http_path: "",
  login_http_method: "POST",
  login_http_body_json: "{}",
  access_token_path: "access_token",
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
  const { t, i18n } = useTranslation();
  const locale: Locale = i18n.language?.startsWith("en") ? "en-US" : "zh-CN";
  const copy = mcpServerCopy[locale];
  const [rows, setRows] = useState<McpServerItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [selectedServer, setSelectedServer] = useState<McpServerItem | null>(null);
  const [selectedToolName, setSelectedToolName] = useState<string>("");
  const [openRegister, setOpenRegister] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [deletingServerId, setDeletingServerId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [registerData, setRegisterData] = useState<McpRegisterFormData>(INITIAL_MCP_REGISTER_DATA);
  const [testData, setTestData] = useState({
    tool_name: "",
    arguments_json: "{\"query\":\"runbook\"}",
  });
  const trimmedServerId = registerData.server_id.trim();
  const existingServer = trimmedServerId
    ? rows.find((item) => item.server_id.toLowerCase() === trimmedServerId.toLowerCase())
    : null;
  const transportType = registerData.transport_type.trim();
  const commandOrUrl = registerData.command.trim();
  const commandLooksLikeShellLine =
    transportType === "stdio" && /[\s|;&<>$`]/.test(commandOrUrl);
  const endpointLooksInvalid =
    ["http", "sse", "streamable_http"].includes(transportType) &&
    commandOrUrl.length > 0 &&
    !commandOrUrl.startsWith("http://") &&
    !commandOrUrl.startsWith("https://");

  const applyRegistrationExample = (example: McpRegistrationExample) => {
    setRegisterData((current) => ({
      ...current,
      ...example.values,
      api_key: "",
      credential_id: "",
      credential_payload_json: "{}",
      login_http_url: "",
      login_http_path: "",
      login_http_method: "POST",
      login_http_body_json: "{}",
      access_token_path: "access_token",
    }));
  };

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
    if (registering) return;
    if (existingServer) {
      setError(copy.alreadyRegistered.replace("{{name}}", existingServer.server_id));
      return;
    }
    setError(null);
    setSuccessMessage(null);
    setRegistering(true);
    const registeredServerId = registerData.server_id.trim();
    try {
      const authType = registerData.auth_type.trim();
      const credentialId = registerData.credential_id.trim() || `mcp-${registeredServerId}-credential`;
      let authConfig: Record<string, unknown> | undefined;
      let authCredential: Record<string, unknown> | undefined;
      if (authType !== "none") {
        authCredential = {
          credential_id: credentialId,
          credential_type: authType,
          secret_payload:
            authType === "api_key"
              ? { api_key: registerData.api_key }
              : JSON.parse(registerData.credential_payload_json || "{}"),
          metadata: { source: "mcp_registration_form" },
        };
        authConfig = {
          type: authType,
          credential_ref: credentialId,
        };
        if (authType === "api_key") {
          if (registerData.transport_type === "stdio") {
            authConfig = {
              ...authConfig,
              env_name: registerData.env_name.trim() || "ZENTEX_MCP_API_KEY",
            };
          } else {
            authConfig = {
              ...authConfig,
              key_name: registerData.header_name.trim() || "X-API-Key",
            };
          }
        }
        if (authType === "login_flow") {
          authConfig = {
            ...authConfig,
            access_token_path: registerData.access_token_path.trim() || "access_token",
            login_http: {
              ...(registerData.login_http_url.trim() ? { url: registerData.login_http_url.trim() } : {}),
              ...(registerData.login_http_path.trim() ? { path: registerData.login_http_path.trim() } : {}),
              method: registerData.login_http_method.trim() || "POST",
              body_template: JSON.parse(registerData.login_http_body_json || "{}"),
            },
          };
        }
      }
      const response = await fetch("/api/web/mcp-servers/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          server_id: registerData.server_id,
          transport_type: registerData.transport_type,
          command: registerData.command,
          args: registerData.args.split(" ").map((item) => item.trim()).filter(Boolean),
          ...(registerData.help_doc_url.trim() ? { help_doc_url: registerData.help_doc_url.trim() } : {}),
          ...(registerData.project_doc_url.trim() ? { project_doc_url: registerData.project_doc_url.trim() } : {}),
          ...(authConfig ? { auth_config: authConfig } : {}),
          ...(authCredential ? { auth_credential: authCredential } : {}),
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        const detail = payload?.detail;
        const message =
          typeof detail === "string"
            ? detail
            : detail?.operator_message || detail?.message || copy.registerFailed;
        throw new Error(formatMcpRegistrationError(message));
      }
      setOpenRegister(false);
      setRegisterData(INITIAL_MCP_REGISTER_DATA);
      setSuccessMessage(copy.registerSuccess.replace("{{name}}", registeredServerId));
      await loadServers();
    } catch (err: any) {
      setSuccessMessage(null);
      setError(err?.message || copy.registerFailed);
    } finally {
      setRegistering(false);
    }
  };

  const formatMcpRegistrationError = (message: string) => {
    if (message.includes("already registered")) {
      return copy.registerErrorAlreadyRegistered;
    }
    if (message.includes("requires command to be an HTTP endpoint")) {
      return copy.registerErrorEndpointInvalid;
    }
    if (message.includes("is not reachable") || message.includes("health probe failed")) {
      return copy.registerErrorUnreachable;
    }
    if (message.includes("Unsupported MCP protocol_version")) {
      return copy.registerErrorProtocol;
    }
    return message;
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

  const updateServerActivation = async (server: McpServerItem, action: "activate" | "disable") => {
    try {
      const response = await fetch(`/api/web/mcp-servers/${encodeURIComponent(server.server_id)}/${action}`, {
        method: "POST",
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.detail || `${action} failed`);
      }
      setSelectedServer((current) => current && current.server_id === server.server_id ? { ...current, ...payload } : current);
      await loadServers();
    } catch (err: any) {
      setError(err?.message || `${action} failed`);
    }
  };

  const deleteServerRegistration = async (server: McpServerItem) => {
    if (!window.confirm(copy.deleteConfirm.replace("{{name}}", server.server_id))) {
      return;
    }
    setDeletingServerId(server.server_id);
    setError(null);
    try {
      const response = await fetch(`/api/web/mcp-servers/${encodeURIComponent(server.server_id)}`, {
        method: "DELETE",
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = payload?.detail;
        const message = typeof detail === "string" ? detail : detail?.operator_message || detail?.message || copy.deleteFailed;
        throw new Error(message);
      }
      setSelectedServer((current) => current && current.server_id === server.server_id ? null : current);
      await loadServers();
    } catch (err: any) {
      setError(err?.message || copy.deleteFailed);
    } finally {
      setDeletingServerId(null);
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
    {
      field: "actions",
      headerName: copy.actions,
      minWidth: 260,
      sortable: false,
      renderCell: (params) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" startIcon={<PowerSettingsNewIcon />} onClick={(event) => {
            event.stopPropagation();
            void updateServerActivation(params.row as McpServerItem, "activate");
          }}>
            激活
          </Button>
          <Button size="small" startIcon={<BlockIcon />} onClick={(event) => {
            event.stopPropagation();
            void updateServerActivation(params.row as McpServerItem, "disable");
          }}>
            关闭
          </Button>
          <Button
            size="small"
            color="error"
            startIcon={<Trash2 size={16} />}
            disabled={deletingServerId === (params.row as McpServerItem).server_id}
            onClick={(event) => {
              event.stopPropagation();
              void deleteServerRegistration(params.row as McpServerItem);
            }}
          >
            {copy.deleteServer}
          </Button>
        </Stack>
      ),
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
        <Stack direction="row" spacing={1}>
          <Button
            component={RouterLink}
            to="/console/module-logs/mcp-servers"
            variant="outlined"
            startIcon={<ArticleIcon />}
          >
            {t("moduleLogs.view")}
          </Button>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => {
              setError(null);
              setSuccessMessage(null);
              setOpenRegister(true);
            }}
          >
            {copy.registerServer}
          </Button>
        </Stack>
      </Stack>

      <Alert severity="info" variant="outlined">
        {copy.pageFunctionHelp}
      </Alert>
      <Alert severity="info" variant="outlined">
        <Stack spacing={1}>
          <Typography variant="subtitle2">{copy.functionOverviewTitle}</Typography>
          <Typography variant="body2">{copy.functionOverviewBody}</Typography>
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            <Chip size="small" variant="outlined" label={copy.functionRegister} />
            <Chip size="small" variant="outlined" label={copy.functionDiscoverTools} />
            <Chip size="small" variant="outlined" label={copy.functionRouteTasks} />
            <Chip size="small" variant="outlined" label={copy.functionInjectAuth} />
            <Chip size="small" variant="outlined" label={copy.functionTestCall} />
            <Chip size="small" variant="outlined" label={copy.functionRuntimeLogs} />
          </Stack>
        </Stack>
      </Alert>

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      ) : null}
      {successMessage ? (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccessMessage(null)}>
          {successMessage}
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
              <Stack direction="row" spacing={1} sx={{ mt: 1 }} useFlexGap flexWrap="wrap">
                <Button size="small" startIcon={<PowerSettingsNewIcon />} onClick={() => void updateServerActivation(selectedServer, "activate")}>
                  激活
                </Button>
                <Button size="small" startIcon={<BlockIcon />} onClick={() => void updateServerActivation(selectedServer, "disable")}>
                  关闭
                </Button>
                <Button
                  size="small"
                  color="error"
                  startIcon={<Trash2 size={16} />}
                  disabled={deletingServerId === selectedServer.server_id}
                  onClick={() => void deleteServerRegistration(selectedServer)}
                >
                  {copy.deleteServer}
                </Button>
              </Stack>
            </Box>
            {selectedServer.error_message ? <Alert severity="warning">{selectedServer.error_message}</Alert> : null}
            {selectedServer.project_doc_url ? (
              <Alert severity="info" variant="outlined">
                {copy.projectDocUrl}: {selectedServer.project_doc_url}
              </Alert>
            ) : null}
            <Divider />
            <Typography variant="h6">{copy.toolList}</Typography>
            {selectedServer.tools.map((tool) => (
              <Box key={tool.mcp_id} sx={{ p: 2, border: "1px solid", borderColor: "divider", borderRadius: 2 }}>
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
                  mcp_id: {tool.mcp_id}
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
              helperText={copy.paramsJsonHelp}
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

      <Dialog open={openRegister} onClose={() => !registering && setOpenRegister(false)} fullWidth maxWidth="sm">
        <DialogTitle>{copy.registerDialogTitle}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Alert severity="info" variant="outlined">
              {copy.registerBasicsHelp}
            </Alert>
            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                {copy.registrationExamplesTitle}
              </Typography>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                {MCP_REGISTRATION_EXAMPLES.map((example) => (
                  <Button
                    key={example.key}
                    size="small"
                    variant="outlined"
                    onClick={() => applyRegistrationExample(example)}
                  >
                    {example.title}
                  </Button>
                ))}
              </Stack>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                {copy.registrationExamplesHelp}
              </Typography>
              <Stack spacing={0.5} sx={{ mt: 1 }}>
                {MCP_REGISTRATION_EXAMPLES.map((example) => (
                  <Typography key={example.key} variant="caption" color="text.secondary">
                    {example.title}: {example.summary}
                  </Typography>
                ))}
              </Stack>
            </Box>
            <TextField
              label={copy.serverId}
              fullWidth
              helperText={copy.serverIdHelp}
              value={registerData.server_id}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setRegisterData({ ...registerData, server_id: e.target.value })
              }
            />
            {existingServer ? (
              <Alert severity="warning" variant="outlined">
                {copy.alreadyRegistered.replace("{{name}}", existingServer.server_id)}
              </Alert>
            ) : null}
            <TextField
              label={copy.transport}
              fullWidth
              helperText={copy.transportHelp}
              value={registerData.transport_type}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setRegisterData({ ...registerData, transport_type: e.target.value })
              }
            />
            <TextField
              label={copy.commandUrl}
              fullWidth
              error={commandLooksLikeShellLine || endpointLooksInvalid}
              helperText={
                commandLooksLikeShellLine
                  ? copy.commandShellLineError
                  : endpointLooksInvalid
                    ? copy.endpointUrlError
                    : copy.commandUrlHelp
              }
              value={registerData.command}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setRegisterData({ ...registerData, command: e.target.value })
              }
            />
            <TextField
              label={copy.argsSpaceSeparated}
              fullWidth
              helperText={copy.argsSpaceSeparatedHelp}
              value={registerData.args}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setRegisterData({ ...registerData, args: e.target.value })
              }
            />
            <TextField
              label={copy.helpDocUrl}
              fullWidth
              helperText={copy.helpDocUrlHelp}
              value={registerData.help_doc_url}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setRegisterData({ ...registerData, help_doc_url: e.target.value })
              }
            />
            <TextField
              label={copy.projectDocUrl}
              fullWidth
              helperText={copy.projectDocUrlHelp}
              value={registerData.project_doc_url}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setRegisterData({ ...registerData, project_doc_url: e.target.value })
              }
            />
            <Divider />
            <Typography variant="subtitle2">{copy.authSettings}</Typography>
            <Typography variant="caption" color="text.secondary">
              {copy.authSettingsHelp}
            </Typography>
            <FormControl fullWidth>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5 }}>
                {copy.authType}
              </Typography>
              <Select
                value={registerData.auth_type}
                onChange={(e) => setRegisterData({ ...registerData, auth_type: e.target.value })}
              >
                <MenuItem value="none">{copy.authNone}</MenuItem>
                <MenuItem value="api_key">{copy.authApiKey}</MenuItem>
                <MenuItem value="login_flow">{copy.authLoginFlow}</MenuItem>
              </Select>
            </FormControl>
            {registerData.auth_type !== "none" ? (
              <>
                <Alert severity="warning" variant="outlined">{copy.authNoInteractiveLogin}</Alert>
                <TextField
                  label={copy.credentialId}
                  fullWidth
                  helperText={copy.credentialIdHelp}
                  value={registerData.credential_id}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setRegisterData({ ...registerData, credential_id: e.target.value })
                  }
                />
              </>
            ) : null}
            {registerData.auth_type === "api_key" ? (
              <>
                <TextField
                  label={copy.apiKeySecret}
                  fullWidth
                  required
                  type="password"
                  helperText={copy.apiKeySecretHelp}
                  value={registerData.api_key}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setRegisterData({ ...registerData, api_key: e.target.value })
                  }
                />
                {registerData.transport_type === "stdio" ? (
                  <TextField
                    label={copy.envName}
                    fullWidth
                    placeholder="ZENTEX_MCP_API_KEY"
                    helperText={copy.envNameHelp}
                    value={registerData.env_name}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                      setRegisterData({ ...registerData, env_name: e.target.value })
                    }
                  />
                ) : (
                  <TextField
                    label={copy.headerName}
                    fullWidth
                    placeholder="X-API-Key"
                    helperText={copy.headerNameHelp}
                    value={registerData.header_name}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                      setRegisterData({ ...registerData, header_name: e.target.value })
                    }
                  />
                )}
              </>
            ) : null}
            {registerData.auth_type === "login_flow" ? (
              <>
                <TextField
                  label={copy.credentialPayloadJson}
                  fullWidth
                  multiline
                  rows={3}
                  helperText={copy.credentialPayloadJsonHelp}
                  value={registerData.credential_payload_json}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setRegisterData({ ...registerData, credential_payload_json: e.target.value })
                  }
                />
                <TextField
                  label={copy.loginHttpUrl}
                  fullWidth
                  helperText={copy.loginHttpUrlHelp}
                  value={registerData.login_http_url}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setRegisterData({ ...registerData, login_http_url: e.target.value })
                  }
                />
                <TextField
                  label={copy.loginHttpPath}
                  fullWidth
                  helperText={copy.loginHttpPathHelp}
                  value={registerData.login_http_path}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setRegisterData({ ...registerData, login_http_path: e.target.value })
                  }
                />
                <TextField
                  label={copy.loginHttpMethod}
                  fullWidth
                  value={registerData.login_http_method}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setRegisterData({ ...registerData, login_http_method: e.target.value })
                  }
                />
                <TextField
                  label={copy.loginHttpBodyJson}
                  fullWidth
                  multiline
                  rows={3}
                  helperText={copy.loginHttpBodyJsonHelp}
                  value={registerData.login_http_body_json}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setRegisterData({ ...registerData, login_http_body_json: e.target.value })
                  }
                />
                <TextField
                  label={copy.accessTokenPath}
                  fullWidth
                  helperText={copy.accessTokenPathHelp}
                  value={registerData.access_token_path}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setRegisterData({ ...registerData, access_token_path: e.target.value })
                  }
                />
              </>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenRegister(false)} disabled={registering}>
            {copy.cancel}
          </Button>
          <Button
            variant="contained"
            onClick={() => void handleRegister()}
            disabled={
              registering ||
              Boolean(existingServer) ||
              commandLooksLikeShellLine ||
              endpointLooksInvalid ||
              !registerData.server_id.trim() ||
              !registerData.command.trim() ||
              (registerData.auth_type === "api_key" && !registerData.api_key.trim()) ||
              (registerData.auth_type === "login_flow" &&
                !registerData.login_http_url.trim() &&
                !registerData.login_http_path.trim())
            }
          >
            {registering ? copy.registering : copy.confirmRegister}
          </Button>
        </DialogActions>
      </Dialog>
      </Stack>
    </Box>
  );
}
