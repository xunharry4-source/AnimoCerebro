import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import HistoryIcon from "@mui/icons-material/History";
import LinkIcon from "@mui/icons-material/Link";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ScienceIcon from "@mui/icons-material/Science";
import {
  formatLocalizedDateTime,
  formatPluginOperationalStatus,
  formatPluginStatus,
  pluginManagementCopy,
  type Locale,
} from "../../i18n";
import {
  bindFunctionalPlugin,
  fetchCognitivePluginDetail,
  fetchFunctionalPlugins,
  forceEnablePlugin,
  testFunctionalPlugin,
  unbindFunctionalPlugin,
  type CognitivePluginDetailResponse,
  type PluginHistoryItem,
  type PluginRow,
  type PluginRelationshipItem,
} from "./pluginsApi";

function getStatusColor(
  status: PluginRow["lifecycle_status"],
): "default" | "success" | "warning" | "error" | "info" {
  switch (status) {
    case "active":
      return "success";
    case "degraded":
      return "warning";
    case "revoked":
      return "error";
    case "sandbox_verified":
      return "info";
    default:
      return "default";
  }
}

function getOperationalStatusColor(
  status: PluginRow["operational_status"],
): "default" | "success" | "warning" | "error" {
  switch (status) {
    case "enabled":
      return "success";
    case "abnormal":
      return "warning";
    case "unavailable":
      return "error";
    default:
      return "default";
  }
}

function HistoryTable({
  history,
  locale,
  actionLoadingPluginId,
  onActivateVersion,
  relatedVersions,
  activeVersionToolId,
}: {
  history: CognitivePluginDetailResponse["history"];
  locale: Locale;
  actionLoadingPluginId: string | null;
  onActivateVersion: (item: PluginHistoryItem) => void;
  relatedVersions: PluginRow[];
  activeVersionToolId: string | null;
}) {
  const { t } = useTranslation();
  const activeVersion = relatedVersions.find((item) => item.tool_id === activeVersionToolId) ?? null;

  if (history.length === 0) {
    return (
      <Stack spacing={2}>
        <Alert severity={activeVersion ? "success" : "warning"}>
          <strong>{pluginManagementCopy[locale].currentRunningVersion}:</strong>{" "}
          {activeVersion ? `${activeVersion.tool_id} · ${activeVersion.version}` : "--"}
        </Alert>
        <Alert severity="info">{pluginManagementCopy[locale].versionActivationRules}</Alert>
        <Alert severity="info">{pluginManagementCopy[locale].noHistoryRecords}</Alert>
      </Stack>
    );
  }

  return (
    <TableContainer component={Paper} variant="outlined">
      <Stack spacing={2} sx={{ mb: 2 }}>
        <Alert severity={activeVersion ? "success" : "warning"}>
          <strong>{pluginManagementCopy[locale].currentRunningVersion}:</strong>{" "}
          {activeVersion ? `${activeVersion.tool_id} · ${activeVersion.version}` : "--"}
        </Alert>
        <Alert severity="info">{pluginManagementCopy[locale].versionActivationRules}</Alert>
      </Stack>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>{t("plugins.version")}</TableCell>
            <TableCell>{t("plugins.upgradeStatus")}</TableCell>
            <TableCell>{pluginManagementCopy[locale].startedAt}</TableCell>
            <TableCell>{pluginManagementCopy[locale].updatedAt}</TableCell>
            <TableCell>{pluginManagementCopy[locale].rollbackConditions}</TableCell>
            <TableCell>{pluginManagementCopy[locale].lastUsedAt}</TableCell>
            <TableCell align="right">{t("plugins.actions")}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {history.map((item) => (
            <TableRow key={`${item.plugin_id}-${item.version}-${item.started_at ?? ""}`}>
              <TableCell>
                <Typography variant="subtitle2">{item.version}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {item.previous_version ? `from ${item.previous_version}` : item.plugin_id}
                </Typography>
                {item.plugin_id === activeVersionToolId ? (
                  <Chip
                    size="small"
                    sx={{ mt: 0.5 }}
                    color="success"
                    label={pluginManagementCopy[locale].activeVersion}
                  />
                ) : null}
              </TableCell>
              <TableCell>
                <Chip size="small" label={item.upgrade_status} variant="outlined" />
              </TableCell>
              <TableCell>{formatLocalizedDateTime(item.started_at, locale)}</TableCell>
              <TableCell>{formatLocalizedDateTime(item.completed_at, locale)}</TableCell>
              <TableCell>{item.error_message || "--"}</TableCell>
              <TableCell>{item.previous_version || "--"}</TableCell>
              <TableCell align="right">
                {item.plugin_id !== activeVersionToolId ? (
                  <Button
                    size="small"
                    variant="contained"
                    disabled={actionLoadingPluginId === item.plugin_id}
                    onClick={() => onActivateVersion(item)}
                  >
                    {pluginManagementCopy[locale].activateThisVersion}
                  </Button>
                ) : null}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function RelationTable({
  rows,
  locale,
  onUnbind,
  onTest,
}: {
  rows: PluginRelationshipItem[];
  locale: Locale;
  onUnbind: (row: PluginRelationshipItem) => void;
  onTest: (row: PluginRelationshipItem) => void;
}) {
  const { t } = useTranslation();
  if (rows.length === 0) {
    return <Alert severity="info">{pluginManagementCopy[locale].noBoundFunctionalPlugins}</Alert>;
  }

  return (
    <TableContainer component={Paper} variant="outlined">
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>{t("plugins.toolId")}</TableCell>
            <TableCell>{t("plugins.version")}</TableCell>
            <TableCell>{t("plugins.lifecycleStatus")}</TableCell>
            <TableCell>{t("plugins.status")}</TableCell>
            <TableCell>{t("plugins.description")}</TableCell>
            <TableCell align="right">{t("plugins.actions")}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.plugin.tool_id} hover>
              <TableCell>
                <Typography variant="subtitle2">{row.plugin.tool_id}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {row.role} / {row.priority}
                </Typography>
              </TableCell>
              <TableCell>{row.plugin.version}</TableCell>
              <TableCell>
                <Chip size="small" label={formatPluginStatus(row.plugin.lifecycle_status, locale)} color={getStatusColor(row.plugin.lifecycle_status)} variant="outlined" />
              </TableCell>
              <TableCell>
                <Chip size="small" label={formatPluginOperationalStatus(row.plugin.operational_status, locale)} color={getOperationalStatusColor(row.plugin.operational_status)} variant="outlined" />
              </TableCell>
              <TableCell>
                <Typography variant="body2" noWrap sx={{ maxWidth: 300 }}>
                  {row.plugin.description}
                </Typography>
              </TableCell>
              <TableCell align="right">
                <Stack direction="row" spacing={1} justifyContent="flex-end">
                  <Button size="small" variant="outlined" startIcon={<ScienceIcon />} onClick={() => onTest(row)}>
                    {pluginManagementCopy[locale].testFunctionalPlugin}
                  </Button>
                  <Button size="small" variant="outlined" color="warning" startIcon={<DeleteOutlineIcon />} onClick={() => onUnbind(row)}>
                    {pluginManagementCopy[locale].unbindFunctionalPlugin}
                  </Button>
                </Stack>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

export default function CognitivePluginDetailPage() {
  const { t, i18n } = useTranslation();
  const { pluginId } = useParams<{ pluginId: string }>();
  const navigate = useNavigate();
  const locale = (i18n.language as Locale) || "zh-CN";
  const [detail, setDetail] = useState<CognitivePluginDetailResponse | null>(null);
  const [functionalPlugins, setFunctionalPlugins] = useState<PluginRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionLoadingPluginId, setActionLoadingPluginId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [bindPluginId, setBindPluginId] = useState("");
  const [bindRole, setBindRole] = useState("primary");
  const [bindPriority, setBindPriority] = useState(1);
  const [bindFallbackId, setBindFallbackId] = useState("");
  const [bindAuditReason, setBindAuditReason] = useState("");

  useEffect(() => {
    if (pluginId) {
      void loadData(pluginId);
    }
  }, [pluginId]);

  const loadData = async (id: string) => {
    setLoading(true);
    try {
      const [detailData, functionalData] = await Promise.all([
        fetchCognitivePluginDetail(id),
        fetchFunctionalPlugins(),
      ]);
      setDetail(detailData);
      setFunctionalPlugins(functionalData);
      setBindPluginId((current) => current || functionalData.find((item) => !detailData.functional_plugins.some((relation) => relation.plugin.tool_id === item.tool_id))?.tool_id || "");
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "加载详情失败");
    } finally {
      setLoading(false);
    }
  };

  const boundFunctionalIds = useMemo(
    () => new Set((detail?.functional_plugins ?? []).map((row) => row.plugin.tool_id)),
    [detail],
  );

  const availableFunctionalPlugins = useMemo(
    () => functionalPlugins.filter((item) => !boundFunctionalIds.has(item.tool_id)),
    [functionalPlugins, boundFunctionalIds],
  );

  useEffect(() => {
    if (!bindPluginId && availableFunctionalPlugins.length > 0) {
      setBindPluginId(availableFunctionalPlugins[0].tool_id);
    }
  }, [availableFunctionalPlugins, bindPluginId]);

  const refresh = async () => {
    if (!pluginId) {
      return;
    }
    await loadData(pluginId);
  };

  const handleBind = async () => {
    if (!pluginId || !bindPluginId || !bindAuditReason.trim()) {
      return;
    }
    setActionLoading(true);
    setActionLoadingPluginId(bindPluginId);
    try {
      await bindFunctionalPlugin(pluginId, bindPluginId, {
        audit_reason: bindAuditReason.trim(),
        role: bindRole,
        priority: bindPriority,
        fallback_id: bindFallbackId.trim() || null,
      });
      setBindAuditReason("");
      setBindFallbackId("");
      await refresh();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "绑定功能插件失败");
    } finally {
      setActionLoading(false);
      setActionLoadingPluginId(null);
    }
  };

  const handleUnbind = async (row: PluginRelationshipItem) => {
    if (!pluginId) {
      return;
    }
    const reason = window.prompt(pluginManagementCopy[locale].auditReasonPrompt);
    if (!reason || !reason.trim()) {
      return;
    }
    setActionLoading(true);
    setActionLoadingPluginId(row.plugin.tool_id);
    try {
      await unbindFunctionalPlugin(pluginId, row.plugin.tool_id, {
        audit_reason: reason.trim(),
        role: row.role,
        priority: row.priority,
        fallback_id: row.fallback_id,
      });
      await refresh();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "解绑功能插件失败");
    } finally {
      setActionLoading(false);
      setActionLoadingPluginId(null);
    }
  };

  const handleTest = async (row: PluginRelationshipItem) => {
    if (!pluginId) {
      return;
    }
    const reason = window.prompt(pluginManagementCopy[locale].auditReasonPrompt);
    if (!reason || !reason.trim()) {
      return;
    }
    setActionLoading(true);
    setActionLoadingPluginId(row.plugin.tool_id);
    try {
      await testFunctionalPlugin(pluginId, row.plugin.tool_id, {
        audit_reason: reason.trim(),
        idempotency_key: crypto.randomUUID(),
      });
      await refresh();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "测试功能插件失败");
    } finally {
      setActionLoading(false);
      setActionLoadingPluginId(null);
    }
  };

  const handleActivateVersion = async (item: PluginHistoryItem) => {
    const reason = window.prompt(pluginManagementCopy[locale].auditReasonPrompt);
    if (!reason || !reason.trim()) {
      return;
    }
    setActionLoading(true);
    try {
      await forceEnablePlugin(item.plugin_id, reason.trim());
      await refresh();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "激活插件版本失败");
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "60vh" }}>
        <CircularProgress />
      </Box>
    );
  }

  if (errorMessage && !detail) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error">{errorMessage}</Alert>
        <Button startIcon={<ArrowBackIcon />} onClick={() => navigate("/console/plugins")} sx={{ mt: 2 }}>
          {pluginManagementCopy[locale].backToPlugins}
        </Button>
      </Box>
    );
  }

  if (!detail) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">未找到插件详情</Alert>
        <Button startIcon={<ArrowBackIcon />} onClick={() => navigate("/console/plugins")} sx={{ mt: 2 }}>
          {pluginManagementCopy[locale].backToPlugins}
        </Button>
      </Box>
    );
  }

  return (
    <Stack spacing={3} sx={{ p: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={2}>
        <Button startIcon={<ArrowBackIcon />} onClick={() => navigate("/console/plugins")} variant="outlined">
          {pluginManagementCopy[locale].backToPlugins}
        </Button>
        <Typography variant="h4" component="h1">
          {detail.plugin.tool_id}
        </Typography>
        <Box sx={{ width: 120 }} />
      </Stack>

      {errorMessage ? <Alert severity="error" onClose={() => setErrorMessage(null)}>{errorMessage}</Alert> : null}

      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            {detail.active_version_tool_id == null ? (
              <Alert severity="warning">{pluginManagementCopy[locale].offlineWarning}</Alert>
            ) : null}
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Chip label={detail.plugin.plugin_kind} variant="outlined" />
              <Chip label={detail.plugin.version} variant="outlined" />
              <Chip label={formatPluginStatus(detail.plugin.lifecycle_status, locale)} color={getStatusColor(detail.plugin.lifecycle_status)} />
              <Chip label={formatPluginOperationalStatus(detail.plugin.operational_status, locale)} color={getOperationalStatusColor(detail.plugin.operational_status)} />
              {detail.plugin.is_default ? <Chip label={t("plugins.defaultPlugin")} color="info" /> : null}
            </Stack>
            <Typography variant="body1" color="text.secondary">
              {detail.plugin.description}
            </Typography>
            <Divider />
            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
              <Box>
                <Typography variant="subtitle2" color="text.secondary">{pluginManagementCopy[locale].purpose}</Typography>
                <Typography variant="body2">{detail.plugin.purpose || pluginManagementCopy[locale].noPurpose}</Typography>
              </Box>
              <Box>
                <Typography variant="subtitle2" color="text.secondary">{pluginManagementCopy[locale].createdAt}</Typography>
                <Typography variant="body2">{formatLocalizedDateTime(detail.plugin.created_at, locale)}</Typography>
              </Box>
              <Box>
                <Typography variant="subtitle2" color="text.secondary">{pluginManagementCopy[locale].updatedAt}</Typography>
                <Typography variant="body2">{formatLocalizedDateTime(detail.plugin.updated_at, locale)}</Typography>
              </Box>
              <Box>
                <Typography variant="subtitle2" color="text.secondary">{pluginManagementCopy[locale].startedAt}</Typography>
                <Typography variant="body2">{formatLocalizedDateTime(detail.plugin.started_at, locale)}</Typography>
              </Box>
            </Stack>
          </Stack>
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <Stack direction="row" spacing={1} alignItems="center">
              <LinkIcon fontSize="small" />
              <Typography variant="h6">{pluginManagementCopy[locale].relationManagement}</Typography>
            </Stack>
            <Typography variant="subtitle2">{pluginManagementCopy[locale].boundFunctionalPlugins}</Typography>
            <RelationTable rows={detail.functional_plugins} locale={locale} onUnbind={handleUnbind} onTest={handleTest} />
            <Divider />
            <Typography variant="subtitle2">{pluginManagementCopy[locale].addFunctionalPlugin}</Typography>
            {availableFunctionalPlugins.length === 0 ? (
              <Alert severity="info">{pluginManagementCopy[locale].noAvailableFunctionalPlugins}</Alert>
            ) : (
              <Stack spacing={2}>
                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                  <FormControl fullWidth>
                    <InputLabel id="bind-functional-label">{pluginManagementCopy[locale].selectFunctionalPlugin}</InputLabel>
                    <Select
                      labelId="bind-functional-label"
                      value={bindPluginId}
                      label={pluginManagementCopy[locale].selectFunctionalPlugin}
                      onChange={(event) => setBindPluginId(event.target.value)}
                    >
                      {availableFunctionalPlugins.map((item) => (
                        <MenuItem key={item.tool_id} value={item.tool_id}>
                          {item.tool_id} · {item.version}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <TextField
                    label={pluginManagementCopy[locale].auditReasonPrompt}
                    value={bindAuditReason}
                    onChange={(event) => setBindAuditReason(event.target.value)}
                    fullWidth
                  />
                </Stack>
                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                  <TextField
                    label="role"
                    value={bindRole}
                    onChange={(event) => setBindRole(event.target.value)}
                    sx={{ minWidth: 180 }}
                  />
                  <TextField
                    label="priority"
                    type="number"
                    value={bindPriority}
                    onChange={(event) => setBindPriority(Number(event.target.value) || 1)}
                    sx={{ width: 140 }}
                  />
                  <TextField
                    label="fallback_id"
                    value={bindFallbackId}
                    onChange={(event) => setBindFallbackId(event.target.value)}
                    fullWidth
                  />
                  <Button
                    variant="contained"
                    onClick={() => void handleBind()}
                    disabled={actionLoading || !bindPluginId || !bindAuditReason.trim()}
                  >
                    {pluginManagementCopy[locale].bindFunctionalPlugin}
                  </Button>
                </Stack>
              </Stack>
            )}
          </Stack>
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <Stack direction="row" spacing={1} alignItems="center">
              <HistoryIcon fontSize="small" />
              <Typography variant="h6">{pluginManagementCopy[locale].versionHistory}</Typography>
            </Stack>
            <HistoryTable
              history={detail.history}
              locale={locale}
              actionLoadingPluginId={actionLoadingPluginId}
              onActivateVersion={handleActivateVersion}
              relatedVersions={detail.related_versions}
              activeVersionToolId={detail.active_version_tool_id}
            />
          </Stack>
        </CardContent>
      </Card>

      <Box sx={{ display: "none" }}>{actionLoading ? "loading" : "idle"}</Box>
    </Stack>
  );
}
