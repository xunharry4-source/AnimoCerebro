import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Alert,
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  Checkbox,
  Divider,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { DataGrid, GridColDef } from "@mui/x-data-grid";
import AddIcon from "@mui/icons-material/Add";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

type CliToolItem = {
  command_name: string;
  description: string;
  mapped_domain: "cognitive" | "execution";
  cli_id: string;
  feature_code: string;
  execution_domain?: string | null;
  read_only: boolean;
  side_effect_free: boolean;
  mutates_state: boolean;
  requires_cloud_audit: boolean;
  status: "active" | "degraded" | "revoked";
};

export default function CliAssetManager() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [rows, setRows] = useState<CliToolItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openRegister, setOpenRegister] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [selectedTool, setSelectedTool] = useState<CliToolItem | null>(null);
  const [testResult, setTestResult] = useState<string | null>(null);

  const [formData, setFormData] = useState({
    tool_name: "",
    command_executable: "",
    description: "",
    read_only_flag: true,
    project_path: "",
    project_name: "",
    project_description: "",
    help_doc_url: "",
    auth_type: "none",
    credential_id: "",
    api_key: "",
    auth_env_name: "",
    credential_payload_json: "{}",
    login_command_executable: "",
    login_command_args: "",
    login_stdin_template: "",
    access_token_path: "access_token",
  });
  const [testData, setTestData] = useState({
    arguments: "",
    stdin_input: "",
    working_directory: "",
  });

  useEffect(() => {
    void loadTools();
  }, []);

  const loadTools = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/web/cli-tools");
      if (!response.ok) {
        throw new Error(t("cli.fetchFailed", { status: response.status }));
      }
      const payload = (await response.json()) as CliToolItem[];
      setRows(payload);
    } catch (err: any) {
      setError(err?.message || t("cli.fetchFailedGeneric"));
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async () => {
    if (registering) return;
    setRegistering(true);
    try {
      const toolName = formData.tool_name.trim();
      const authType = formData.auth_type.trim();
      const credentialId = formData.credential_id.trim() || `cli-${toolName}-credential`;
      let authConfig: Record<string, unknown> | undefined;
      if (authType !== "none") {
        let secretPayload: Record<string, unknown>;
        if (authType === "api_key") {
          secretPayload = { api_key: formData.api_key };
        } else {
          secretPayload = JSON.parse(formData.credential_payload_json || "{}") as Record<string, unknown>;
        }
        const credentialResponse = await fetch(`/api/web/integrations/cli/${encodeURIComponent(toolName)}/credentials`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            credential_id: credentialId,
            credential_type: authType,
            secret_payload: secretPayload,
            metadata: { source: "cli_registration_form" },
          }),
        });
        const credentialPayload = await credentialResponse.json();
        if (!credentialResponse.ok) {
          throw new Error(credentialPayload?.detail || t("cli.credentialSaveFailed"));
        }
        authConfig = {
          type: authType,
          credential_ref: credentialId,
          ...(formData.auth_env_name.trim() ? { env_name: formData.auth_env_name.trim() } : {}),
        };
        if (authType === "login_flow") {
          authConfig = {
            ...authConfig,
            access_token_path: formData.access_token_path.trim() || "access_token",
            login_command: {
              command_executable: formData.login_command_executable.trim(),
              args: formData.login_command_args.split(" ").map((item) => item.trim()).filter(Boolean),
              ...(formData.login_stdin_template ? { stdin_template: formData.login_stdin_template } : {}),
            },
          };
        }
      }
      const payload = {
        tool_name: toolName,
        command_executable: formData.command_executable.trim(),
        description: formData.description.trim(),
        read_only_flag: formData.read_only_flag,
        ...(authConfig ? { auth_config: authConfig } : {}),
        ...(formData.project_path.trim() ? { project_path: formData.project_path.trim() } : {}),
        ...(formData.project_name.trim() ? { project_name: formData.project_name.trim() } : {}),
        ...(formData.project_description.trim() ? { project_description: formData.project_description.trim() } : {}),
        ...(formData.help_doc_url.trim() ? { help_doc_url: formData.help_doc_url.trim() } : {}),
      };
      const response = await fetch("/api/web/cli-tools/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const detail = await response.json();
        const errorDetail = detail?.detail;
        const message =
          typeof errorDetail === "string"
            ? errorDetail
            : errorDetail?.operator_message || errorDetail?.message || t("cli.registerFailed");
        throw new Error(message);
      }
      setOpenRegister(false);
      setFormData({
        tool_name: "",
        command_executable: "",
        description: "",
        read_only_flag: true,
        project_path: "",
        project_name: "",
        project_description: "",
        help_doc_url: "",
        auth_type: "none",
        credential_id: "",
        api_key: "",
        auth_env_name: "",
        credential_payload_json: "{}",
        login_command_executable: "",
        login_command_args: "",
        login_stdin_template: "",
        access_token_path: "access_token",
      });
      void loadTools();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setRegistering(false);
    }
  };

  const handleTestCall = async () => {
    if (!selectedTool) return;
    setTestResult(null);
    try {
      const response = await fetch(`/api/web/cli-tools/${selectedTool.command_name}/test-call`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          arguments: testData.arguments
            .split(" ")
            .map((item) => item.trim())
            .filter(Boolean),
          stdin_input: testData.stdin_input || null,
          working_directory: testData.working_directory || null,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.detail || t("cli.testCallFailed"));
      }
      setTestResult(JSON.stringify(payload, null, 2));
    } catch (err: any) {
      setTestResult(err?.message || t("cli.testCallFailed"));
    }
  };

  const columns: GridColDef[] = [
    {
      field: "command_name",
      headerName: t("cli.toolName"),
      flex: 1,
      minWidth: 150,
      renderCell: (params) => (
        <Box
          sx={{
            color: "primary.main",
            cursor: "pointer",
            textDecoration: "underline",
            "&:hover": { color: "primary.dark" },
          }}
          onClick={() => navigate(`/console/cli-tools/${params.value}`)}
        >
          {params.value}
        </Box>
      ),
    },
    { field: "description", headerName: t("cli.formDescription"), flex: 1.5, minWidth: 220 },
    {
      field: "mapped_domain",
      headerName: t("cli.domainPermission"),
      flex: 1,
      minWidth: 150,
      renderCell: (params) => (
        <Chip
          label={params.value === "cognitive" ? t("cli.domainCognitive") : t("cli.domainExecution")}
          color={params.value === "cognitive" ? "primary" : "error"}
          size="small"
        />
      ),
    },
    {
      field: "status",
      headerName: t("common.status"),
      flex: 1,
      minWidth: 120,
      renderCell: (params) => (
        <Chip
          label={params.value}
          color={params.value === "active" ? "success" : "warning"}
          size="small"
          variant="outlined"
        />
      ),
    },
    { field: "feature_code", headerName: t("cli.featureCode"), flex: 1.5, minWidth: 250 },
    {
      field: "actions",
      headerName: t("common.actions"),
      minWidth: 120,
      sortable: false,
      renderCell: (params) => (
        <Button size="small" onClick={() => setSelectedTool(params.row as CliToolItem)}>
          {t("cli.testCall")}
        </Button>
      ),
    },
  ];

  if (loading) return <CircularProgress sx={{ m: 4 }} />;

  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={3}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Box>
          <Typography variant="h4" gutterBottom>
            {t("cli.assetManagementTitle")}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t("cli.assetManagementSubtitle")}
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setOpenRegister(true)}>
          {t("cli.registerNewTool")}
        </Button>
      </Stack>

      <Alert severity="info" variant="outlined">
        {t("cli.pageFunctionHelp")}
      </Alert>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <DataGrid
        autoHeight
        rows={rows}
        columns={columns}
        getRowId={(row) => row.cli_id || row.command_name}
        sx={{ bgcolor: "background.paper" }}
      />

      <Dialog open={openRegister} onClose={() => setOpenRegister(false)} fullWidth maxWidth="sm">
        <DialogTitle>{t("cli.registerDialogTitle")}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={3} sx={{ mt: 1 }}>
            <Alert severity="info" variant="outlined">
              {t("cli.registerBasicsHelp")}
            </Alert>
            <TextField
              label={t("cli.formToolName")}
              fullWidth
              required
              helperText={t("cli.formToolNameHelp")}
              value={formData.tool_name}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, tool_name: e.target.value })}
            />
            <TextField
              label={t("cli.formCommandExecutable")}
              fullWidth
              required
              placeholder={t("cli.formCommandPlaceholder")}
              helperText={t("cli.formCommandExecutableHelp")}
              value={formData.command_executable}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, command_executable: e.target.value })}
            />
            <TextField
              label={t("cli.formDescription")}
              fullWidth
              required
              multiline
              rows={2}
              helperText={t("cli.formDescriptionHelp")}
              value={formData.description}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, description: e.target.value })}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={formData.read_only_flag}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, read_only_flag: e.target.checked })}
                />
              }
              label={t("cli.formReadOnlyFlag")}
            />
            <Alert severity="info" variant="outlined">
              {formData.read_only_flag 
                ? t("cli.alertReadOnly") 
                : t("cli.alertReadWrite")}
            </Alert>
            <Accordion disableGutters>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Box>
                  <Typography variant="subtitle2">{t("cli.advancedSettings")}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {t("cli.advancedSettingsHelp")}
                  </Typography>
                </Box>
              </AccordionSummary>
              <AccordionDetails>
                <Stack spacing={2}>
                  <TextField
                    label={t("cli.formProjectPath")}
                    fullWidth
                    placeholder={t("cli.formProjectPathPlaceholder")}
                    helperText={t("cli.formProjectPathHelp")}
                    value={formData.project_path}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, project_path: e.target.value })}
                  />
                  <TextField
                    label={t("cli.formProjectName")}
                    fullWidth
                    helperText={t("cli.formProjectNameHelp")}
                    value={formData.project_name}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, project_name: e.target.value })}
                  />
                  <TextField
                    label={t("cli.formProjectDescription")}
                    fullWidth
                    multiline
                    rows={2}
                    helperText={t("cli.formProjectDescriptionHelp")}
                    value={formData.project_description}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                      setFormData({ ...formData, project_description: e.target.value })
                    }
                  />
                  <TextField
                    label={t("cli.formHelpDocUrl")}
                    fullWidth
                    helperText={t("cli.formHelpDocUrlHelp")}
                    value={formData.help_doc_url}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, help_doc_url: e.target.value })}
                  />
                </Stack>
              </AccordionDetails>
            </Accordion>
            <Accordion disableGutters>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Box>
                  <Typography variant="subtitle2">{t("cli.authSettings")}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {t("cli.authSettingsHelp")}
                  </Typography>
                </Box>
              </AccordionSummary>
              <AccordionDetails>
                <Stack spacing={2}>
                  <FormControl fullWidth>
                    <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5 }}>
                      {t("cli.authType")}
                    </Typography>
                    <Select
                      value={formData.auth_type}
                      onChange={(e) => setFormData({ ...formData, auth_type: e.target.value })}
                    >
                      <MenuItem value="none">{t("cli.authNone")}</MenuItem>
                      <MenuItem value="api_key">{t("cli.authApiKey")}</MenuItem>
                      <MenuItem value="login_flow">{t("cli.authLoginFlow")}</MenuItem>
                    </Select>
                  </FormControl>
                  {formData.auth_type !== "none" ? (
                    <>
                      <Alert severity="warning" variant="outlined">{t("cli.authNoInteractiveLogin")}</Alert>
                      <TextField
                        label={t("cli.credentialId")}
                        fullWidth
                        helperText={t("cli.credentialIdHelp")}
                        value={formData.credential_id}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                          setFormData({ ...formData, credential_id: e.target.value })
                        }
                      />
                      <TextField
                        label={t("cli.authEnvName")}
                        fullWidth
                        placeholder={formData.auth_type === "api_key" ? "ZENTEX_CLI_API_KEY / GEMINI_API_KEY" : "ZENTEX_CLI_ACCESS_TOKEN"}
                        helperText={t("cli.authEnvNameHelp")}
                        value={formData.auth_env_name}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                          setFormData({ ...formData, auth_env_name: e.target.value })
                        }
                      />
                    </>
                  ) : null}
                  {formData.auth_type === "api_key" ? (
                    <TextField
                      label={t("cli.apiKeySecret")}
                      fullWidth
                      required
                      type="password"
                      helperText={t("cli.apiKeySecretHelp")}
                      value={formData.api_key}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, api_key: e.target.value })}
                    />
                  ) : null}
                  {formData.auth_type === "login_flow" ? (
                    <>
                      <TextField
                        label={t("cli.credentialPayloadJson")}
                        fullWidth
                        multiline
                        rows={3}
                        value={formData.credential_payload_json}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                          setFormData({ ...formData, credential_payload_json: e.target.value })
                        }
                      />
                      <TextField
                        label={t("cli.loginCommandExecutable")}
                        fullWidth
                        required
                        value={formData.login_command_executable}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                          setFormData({ ...formData, login_command_executable: e.target.value })
                        }
                      />
                      <TextField
                        label={t("cli.loginCommandArgs")}
                        fullWidth
                        value={formData.login_command_args}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                          setFormData({ ...formData, login_command_args: e.target.value })
                        }
                      />
                      <TextField
                        label={t("cli.loginStdinTemplate")}
                        fullWidth
                        multiline
                        rows={2}
                        value={formData.login_stdin_template}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                          setFormData({ ...formData, login_stdin_template: e.target.value })
                        }
                      />
                      <TextField
                        label={t("cli.accessTokenPath")}
                        fullWidth
                        value={formData.access_token_path}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                          setFormData({ ...formData, access_token_path: e.target.value })
                        }
                      />
                    </>
                  ) : null}
                </Stack>
              </AccordionDetails>
            </Accordion>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenRegister(false)}>{t("common.cancel")}</Button>
          <Button
            variant="contained"
            onClick={handleRegister}
            disabled={
              registering ||
              !formData.tool_name.trim() ||
              !formData.command_executable.trim() ||
              !formData.description.trim() ||
              (formData.auth_type === "api_key" && !formData.api_key.trim()) ||
              (formData.auth_type === "login_flow" && !formData.login_command_executable.trim())
            }
          >
            {registering ? t("cli.registering") : t("cli.confirmRegister")}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(selectedTool)} onClose={() => setSelectedTool(null)} fullWidth maxWidth="md">
        <DialogTitle>{t("cli.testCallDialogTitle")}</DialogTitle>
        <DialogContent dividers>
          {selectedTool ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <Typography variant="subtitle1">{selectedTool.command_name}</Typography>
              <Typography variant="body2" color="text.secondary">
                {selectedTool.description}
              </Typography>
              <Divider />
              <TextField
                label={t("cli.testArguments")}
                fullWidth
                helperText={t("cli.testArgumentsHelp")}
                value={testData.arguments}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTestData({ ...testData, arguments: e.target.value })}
              />
              <TextField
                label={t("cli.testStdinInput")}
                fullWidth
                multiline
                rows={3}
                helperText={t("cli.testStdinInputHelp")}
                value={testData.stdin_input}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTestData({ ...testData, stdin_input: e.target.value })}
              />
              <TextField
                label={t("cli.testWorkingDirectory")}
                fullWidth
                helperText={t("cli.testWorkingDirectoryHelp")}
                value={testData.working_directory}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setTestData({ ...testData, working_directory: e.target.value })
                }
              />
              {testResult ? (
                <Alert severity="info">
                  <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{testResult}</pre>
                </Alert>
              ) : null}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSelectedTool(null)}>{t("common.close")}</Button>
          <Button variant="contained" onClick={() => void handleTestCall()} disabled={!selectedTool}>
            {t("cli.executeTest")}
          </Button>
        </DialogActions>
      </Dialog>
      </Stack>
    </Box>
  );
}
