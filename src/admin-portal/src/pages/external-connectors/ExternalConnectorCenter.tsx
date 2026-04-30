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
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { DataGrid, GridColDef } from "@mui/x-data-grid";
import AddIcon from "@mui/icons-material/Add";
import HealthAndSafetyIcon from "@mui/icons-material/HealthAndSafety";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import DescriptionIcon from "@mui/icons-material/Description";

type ConnectorType = "api_app" | "desktop_app" | "browser_app" | "file_app" | "service_bridge" | "sdk_app";

type ConnectorRecord = {
  connector_id: string;
  connector_type: ConnectorType;
  target_app: string;
  display_name: string;
  description: string;
  status: "active" | "degraded" | "revoked";
  profile_level: "minimal" | "described" | "verifiable" | "governed";
  manifest_path?: string | null;
  manifest_hash?: string | null;
  capabilities: Array<{ name: string; read_only: boolean; risk_level: string; profile_level?: string; verification_mode?: string }>;
};

type ManifestCard = {
  valid: boolean;
  errors: string[];
  relative_path: string;
  manifest_hash?: string | null;
  manifest: {
    connector_id?: string;
    name?: string;
    runtime?: string;
    profile_level?: string;
    capabilities?: unknown[];
  };
};

const TYPE_OPTIONS: ConnectorType[] = ["api_app", "desktop_app", "browser_app", "file_app", "service_bridge", "sdk_app"];

export default function ExternalConnectorCenter() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<ConnectorRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [manifestError, setManifestError] = useState<string | null>(null);
  const [manifests, setManifests] = useState<ManifestCard[]>([]);
  const [openRegister, setOpenRegister] = useState(false);
  const [selected, setSelected] = useState<ConnectorRecord | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [form, setForm] = useState({
    connector_id: "",
    connector_type: "file_app" as ConnectorType,
    target_app: "office.word",
    display_name: "",
    description: "",
    base_path: "",
  });
  const [testForm, setTestForm] = useState({
    capability: "read_document",
    path: "",
    content: "",
    output_path: "",
  });

  useEffect(() => {
    void loadConnectors();
  }, []);

  const loadConnectors = async () => {
    setLoading(true);
    setError(null);
    setManifestError(null);
    try {
      const response = await fetch("/api/web/external-connectors");
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.detail?.operator_message || t("externalConnectors.fetchFailed"));
      }
      setRows(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("externalConnectors.fetchFailed"));
    } finally {
      setLoading(false);
    }
    try {
      const manifestResponse = await fetch("/api/web/external-connectors/plugin-manifests");
      const manifestPayload = await manifestResponse.json();
      if (!manifestResponse.ok) {
        throw new Error(manifestPayload?.detail?.operator_message || t("externalConnectors.manifestFetchFailed"));
      }
      setManifests(manifestPayload);
    } catch (err) {
      setManifestError(err instanceof Error ? err.message : t("externalConnectors.manifestFetchFailed"));
    }
  };

  const registerConnector = async () => {
    const body = {
      connector_id: form.connector_id,
      connector_type: form.connector_type,
      target_app: form.target_app,
      display_name: form.display_name,
      description: form.description,
      connection_config: form.base_path ? { base_path: form.base_path } : {},
      auth_config: {},
      permission_scope: {},
      capabilities: [],
    };
    const response = await fetch("/api/web/external-connectors", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload?.detail?.operator_message || t("externalConnectors.registerFailed"));
    }
    setOpenRegister(false);
    setForm({
      connector_id: "",
      connector_type: "file_app",
      target_app: "office.word",
      display_name: "",
      description: "",
      base_path: "",
    });
    await loadConnectors();
  };

  const runHealth = async (connector: ConnectorRecord) => {
    const response = await fetch(`/api/web/external-connectors/${connector.connector_id}/health`);
    const payload = await response.json();
    setResult(JSON.stringify(payload, null, 2));
  };

  const registerFromManifest = async (manifest: ManifestCard) => {
    const response = await fetch("/api/web/external-connectors/register-from-manifest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ manifest_path: manifest.relative_path }),
    });
    const payload = await response.json();
    if (!response.ok) {
      setError(payload?.detail?.operator_message || t("externalConnectors.manifestRegisterFailed"));
      return;
    }
    setResult(JSON.stringify(payload, null, 2));
    await loadConnectors();
  };

  const runTestCall = async () => {
    if (!selected) return;
    const response = await fetch(`/api/web/external-connectors/${selected.connector_id}/test-call`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        capability: testForm.capability,
        arguments: {
          path: testForm.path,
          content: testForm.content,
          output_path: testForm.output_path,
        },
      }),
    });
    const payload = await response.json();
    setResult(JSON.stringify(payload, null, 2));
  };

  const columns: GridColDef[] = [
    { field: "connector_id", headerName: t("externalConnectors.connectorId"), flex: 1.2, minWidth: 180 },
    { field: "display_name", headerName: t("externalConnectors.name"), flex: 1, minWidth: 160 },
    { field: "target_app", headerName: t("externalConnectors.targetApp"), flex: 1, minWidth: 150 },
    {
      field: "connector_type",
      headerName: t("externalConnectors.type"),
      flex: 0.8,
      minWidth: 140,
      renderCell: (params) => <Chip size="small" label={params.value} variant="outlined" />,
    },
    {
      field: "status",
      headerName: t("common.status"),
      flex: 0.7,
      minWidth: 100,
      renderCell: (params) => (
        <Chip size="small" label={params.value} color={params.value === "active" ? "success" : "warning"} />
      ),
    },
    {
      field: "profile_level",
      headerName: t("externalConnectors.profile"),
      flex: 0.7,
      minWidth: 110,
      renderCell: (params) => <Chip size="small" label={params.value ?? "minimal"} variant="outlined" />,
    },
    {
      field: "capabilities",
      headerName: t("externalConnectors.capabilityCount"),
      flex: 0.6,
      minWidth: 90,
      valueGetter: (value: ConnectorRecord["capabilities"] | undefined) => value?.length ?? 0,
    },
    {
      field: "actions",
      headerName: t("common.actions"),
      minWidth: 210,
      sortable: false,
      renderCell: (params) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" startIcon={<HealthAndSafetyIcon />} onClick={() => runHealth(params.row)}>
            {t("externalConnectors.health")}
          </Button>
          <Button size="small" startIcon={<PlayArrowIcon />} onClick={() => setSelected(params.row)}>
            {t("externalConnectors.test")}
          </Button>
        </Stack>
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
              {t("externalConnectors.title")}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t("externalConnectors.subtitle")}
            </Typography>
          </Box>
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setOpenRegister(true)}>
            {t("externalConnectors.register")}
          </Button>
        </Stack>

        <Alert severity="info" variant="outlined">
          {t("externalConnectors.pageFunctionHelp")}
        </Alert>

        {error && <Alert severity="error">{error}</Alert>}
        {manifestError && <Alert severity="warning">{manifestError}</Alert>}

        {manifests.length > 0 && (
          <Stack spacing={1}>
            <Typography variant="h6">{t("externalConnectors.manifestCards")}</Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {manifests.map((manifest) => (
                <Chip
                  key={manifest.relative_path}
                  icon={<DescriptionIcon />}
                  label={`${manifest.manifest.name || manifest.manifest.connector_id || manifest.relative_path} · ${manifest.manifest.profile_level || "minimal"}`}
                  color={manifest.valid ? "default" : "error"}
                  onClick={() => void registerFromManifest(manifest)}
                  variant="outlined"
                />
              ))}
            </Stack>
          </Stack>
        )}

        <DataGrid
          autoHeight
          rows={rows}
          columns={columns}
          getRowId={(row) => row.connector_id}
          disableRowSelectionOnClick
          pageSizeOptions={[10, 25, 50]}
          initialState={{ pagination: { paginationModel: { pageSize: 10, page: 0 } } }}
        />

        {result && (
          <Alert severity="info">
            <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{result}</pre>
          </Alert>
        )}
      </Stack>

      <Dialog open={openRegister} onClose={() => setOpenRegister(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t("externalConnectors.registerDialogTitle")}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Alert severity="info" variant="outlined">
              {t("externalConnectors.registerBasicsHelp")}
            </Alert>
            <TextField label={t("externalConnectors.connectorId")} helperText={t("externalConnectors.connectorIdHelp")} value={form.connector_id} onChange={(e) => setForm({ ...form, connector_id: e.target.value })} />
            <TextField select label={t("externalConnectors.type")} helperText={t("externalConnectors.typeHelp")} value={form.connector_type} onChange={(e) => setForm({ ...form, connector_type: e.target.value as ConnectorType })}>
              {TYPE_OPTIONS.map((option) => (
                <MenuItem key={option} value={option}>
                  {option}
                </MenuItem>
              ))}
            </TextField>
            <TextField label={t("externalConnectors.targetApp")} helperText={t("externalConnectors.targetAppHelp")} value={form.target_app} onChange={(e) => setForm({ ...form, target_app: e.target.value })} />
            <TextField label={t("externalConnectors.name")} helperText={t("externalConnectors.nameHelp")} value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
            <TextField label={t("externalConnectors.description")} helperText={t("externalConnectors.descriptionHelp")} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            <TextField label={t("externalConnectors.basePath")} helperText={t("externalConnectors.basePathHelp")} value={form.base_path} onChange={(e) => setForm({ ...form, base_path: e.target.value })} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenRegister(false)}>{t("common.cancel")}</Button>
          <Button
            variant="contained"
            onClick={() => {
              registerConnector().catch((err) => setError(err instanceof Error ? err.message : t("externalConnectors.registerFailed")));
            }}
          >
            {t("externalConnectors.register")}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(selected)} onClose={() => setSelected(null)} maxWidth="sm" fullWidth>
        <DialogTitle>{t("externalConnectors.testDialogTitle")}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Alert severity="info" variant="outlined">
              {t("externalConnectors.testCallHelp")}
            </Alert>
            <TextField label={t("externalConnectors.capability")} helperText={t("externalConnectors.capabilityHelp")} value={testForm.capability} onChange={(e) => setTestForm({ ...testForm, capability: e.target.value })} />
            <TextField label={t("externalConnectors.filePath")} helperText={t("externalConnectors.filePathHelp")} value={testForm.path} onChange={(e) => setTestForm({ ...testForm, path: e.target.value })} />
            <TextField label={t("externalConnectors.writeContent")} helperText={t("externalConnectors.writeContentHelp")} value={testForm.content} onChange={(e) => setTestForm({ ...testForm, content: e.target.value })} />
            <TextField label={t("externalConnectors.outputPath")} helperText={t("externalConnectors.outputPathHelp")} value={testForm.output_path} onChange={(e) => setTestForm({ ...testForm, output_path: e.target.value })} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSelected(null)}>{t("common.close")}</Button>
          <Button variant="contained" onClick={() => void runTestCall()}>
            {t("externalConnectors.execute")}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
