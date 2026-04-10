import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
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
  FormControlLabel,
  Checkbox,
  Divider,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { DataGrid, GridColDef } from "@mui/x-data-grid";
import AddIcon from "@mui/icons-material/Add";

type CliToolItem = {
  command_name: string;
  description: string;
  mapped_domain: "cognitive" | "execution";
  plugin_id: string;
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
    try {
      const response = await fetch("/api/web/cli-tools/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });
      if (!response.ok) {
        const detail = await response.json();
        throw new Error(detail?.detail || t("cli.registerFailed"));
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
      });
      void loadTools();
    } catch (err: any) {
      alert(err.message);
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

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <DataGrid
        autoHeight
        rows={rows.map((r, i) => ({ id: r.plugin_id || i, ...r }))}
        columns={columns}
        sx={{ bgcolor: "background.paper" }}
      />

      <Dialog open={openRegister} onClose={() => setOpenRegister(false)} fullWidth maxWidth="sm">
        <DialogTitle>{t("cli.registerDialogTitle")}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={3} sx={{ mt: 1 }}>
            <TextField
              label={t("cli.formToolName")}
              fullWidth
              value={formData.tool_name}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, tool_name: e.target.value })}
            />
            <TextField
              label={t("cli.formCommandExecutable")}
              fullWidth
              placeholder={t("cli.formCommandPlaceholder")}
              value={formData.command_executable}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, command_executable: e.target.value })}
            />
            <TextField
              label={t("cli.formDescription")}
              fullWidth
              multiline
              rows={2}
              value={formData.description}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, description: e.target.value })}
            />
            <TextField
              label={t("cli.formProjectPath")}
              fullWidth
              value={formData.project_path}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, project_path: e.target.value })}
            />
            <TextField
              label={t("cli.formProjectName")}
              fullWidth
              value={formData.project_name}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, project_name: e.target.value })}
            />
            <TextField
              label={t("cli.formProjectDescription")}
              fullWidth
              multiline
              rows={2}
              value={formData.project_description}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setFormData({ ...formData, project_description: e.target.value })
              }
            />
            <TextField
              label={t("cli.formHelpDocUrl")}
              fullWidth
              value={formData.help_doc_url}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, help_doc_url: e.target.value })}
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
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenRegister(false)}>{t("common.cancel")}</Button>
          <Button variant="contained" onClick={handleRegister} disabled={!formData.tool_name || !formData.command_executable}>
            {t("cli.confirmRegister")}
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
                value={testData.arguments}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTestData({ ...testData, arguments: e.target.value })}
              />
              <TextField
                label={t("cli.testStdinInput")}
                fullWidth
                multiline
                rows={3}
                value={testData.stdin_input}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTestData({ ...testData, stdin_input: e.target.value })}
              />
              <TextField
                label={t("cli.testWorkingDirectory")}
                fullWidth
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
