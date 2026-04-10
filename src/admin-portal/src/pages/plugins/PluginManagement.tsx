import { useEffect, useMemo, useState } from "react";
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
  FormControlLabel,
  InputLabel,
  List,
  ListItem,
  ListItemText,
  Paper,
  MenuItem,
  Select,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
  Tabs,
  Tab,
} from "@mui/material";
import {
  type Locale,
  formatHealthStatus,
  formatLocalizedDateTime,
  formatPluginBindingStatus,
  formatPluginDescriptor,
  formatPluginStatus,
  pluginManagementCopy,
} from "../../i18n";
import { useTranslation } from "react-i18next";

type CognitivePluginRow = {
  tool_id: string;
  feature_code: string;
  supports_multiple_plugins: boolean;
  plugin_kind: string;
  version: string;
  status: "candidate" | "active" | "degraded" | "revoked" | "sandbox_verified";
  health_status: string | null;
  purpose: string;
  description: string;
  used_in: string[];
  is_default: boolean;
  is_official_release: boolean;
  can_force_enable: boolean;
  can_force_disable: boolean;
  can_delete: boolean;
  usage_count: number;
  failure_count: number;
  rollback_conditions: string[];
  trigger_conditions: string[];
  required_context: string[];
  created_at: string | null;
  updated_at: string | null;
  started_at: string | null;
  stopped_at: string | null;
  last_used_at: string | null;
};

type ForceEnableResponse = {
  plugin: CognitivePluginRow;
  auto_disabled_plugin_ids: string[];
  requires_override_warning: boolean;
  message: string;
};

type PluginFeatureGroup = {
  feature_code: string;
  display_name: string;
  plugin_kind: string;
  feature_guide_path: string | null;
  family_guide_path: string | null;
  supports_multiple_plugins: boolean;
  binding_status: "bound_active" | "bound_inactive" | "unbound";
  active_plugin_ids: string[];
  plugins: CognitivePluginRow[];
};

type PendingForceEnable = {
  pluginId: string;
  activePluginIds: string[];
};

function getStatusColor(
  status: CognitivePluginRow["status"],
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

function getBindingStatusColor(
  status: PluginFeatureGroup["binding_status"],
): "success" | "warning" | "default" {
  switch (status) {
    case "bound_active":
      return "success";
    case "bound_inactive":
      return "warning";
    default:
      return "default";
  }
}

export default function PluginManagement() {
  const { t, i18n } = useTranslation();
  const [locale, setLocale] = useState<Locale>(i18n.language as Locale || "zh-CN");
  const [groups, setGroups] = useState<PluginFeatureGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [selectedPlugin, setSelectedPlugin] = useState<CognitivePluginRow | null>(null);
  const [pendingForceEnable, setPendingForceEnable] = useState<PendingForceEnable | null>(null);
  const [forceEnableAuditReason, setForceEnableAuditReason] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | CognitivePluginRow["status"]>("all");
  const [selectedFeatureCode, setSelectedFeatureCode] = useState<string | null>(null);
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
  const [refreshIntervalMs, setRefreshIntervalMs] = useState<10000 | 30000 | 60000>(10000);
  const [activeTab, setActiveTab] = useState<"cognitive" | "functional">("cognitive");

  const loadPlugins = async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/web/plugins", {
        method: "GET",
        headers: {
          Accept: "application/json",
        },
      });

      if (!response.ok) {
        throw new Error(`request_failed_${response.status}`);
      }

      const payload = (await response.json()) as PluginFeatureGroup[];
      setGroups(payload);
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(pluginManagementCopy[locale].backendError);
    } finally {
      setLoading(false);
    }
  };

  const runPluginAction = async (
    pluginId: string,
    action: "force-enable" | "force-disable" | "delete",
    auditReasonOverride?: string,
  ) => {
    const auditReason = auditReasonOverride ?? window.prompt(text.auditReasonPrompt);
    if (!auditReason || !auditReason.trim()) {
      return;
    }

    try {
      const response = await fetch(
        action === "force-enable"
          ? `/api/web/plugins/${pluginId}/force-enable`
          : action === "force-disable"
            ? `/api/web/plugins/${pluginId}/force-disable`
          : `/api/web/plugins/${pluginId}`,
        {
          method: action === "delete" ? "DELETE" : "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify({ audit_reason: auditReason.trim() }),
        },
      );

      if (!response.ok) {
        throw new Error(`plugin_action_failed_${response.status}`);
      }

      if (action === "force-enable") {
        const payload = (await response.json()) as ForceEnableResponse;
        setActionMessage(
          payload.auto_disabled_plugin_ids.length > 0
            ? `${text.actionSuccessForceEnableWithAutoDisablePrefix}${payload.auto_disabled_plugin_ids.join(inlineSeparator)}`
            : text.actionSuccessForceEnable,
        );
      } else {
        setActionMessage(
          action === "force-disable"
            ? text.actionSuccessForceDisable
            : text.actionSuccessDelete,
        );
      }
      await loadPlugins();
    } catch {
      setActionMessage(text.actionFailed);
    }
  };

  useEffect(() => {
    void loadPlugins();
  }, []);

  useEffect(() => {
    if (!autoRefreshEnabled) {
      return undefined;
    }

    const timerId = window.setInterval(() => {
      void loadPlugins();
    }, refreshIntervalMs);

    return () => {
      window.clearInterval(timerId);
    };
  }, [autoRefreshEnabled, refreshIntervalMs]);

  const rows = useMemo(() => groups.flatMap((group) => group.plugins), [groups]);

  const filteredRows = useMemo(
    () =>
      rows.filter((row) => {
        const matchesSearch =
          searchQuery.trim() === "" ||
          row.tool_id.toLowerCase().includes(searchQuery.trim().toLowerCase());
        const matchesStatus = statusFilter === "all" || row.status === statusFilter;
        return matchesSearch && matchesStatus;
      }),
    [rows, searchQuery, statusFilter],
  );

  const cognitiveGroups = useMemo(
    () => groups.filter((group) => group.plugin_kind === "cognitive_tool"),
    [groups],
  );

  const functionalGroups = useMemo(
    () => groups.filter((group) => group.plugin_kind !== "cognitive_tool"),
    [groups],
  );

  const currentGroups = activeTab === "cognitive" ? cognitiveGroups : functionalGroups;

  const alertRows = useMemo(
    () => rows.filter((row) => row.status === "degraded" || row.status === "revoked"),
    [rows],
  );
  const filteredGroups = useMemo(
    () =>
      currentGroups
        .map((group) => ({
          ...group,
          plugins:
            searchQuery.trim() === "" && statusFilter === "all"
              ? group.plugins
              : group.plugins.filter((plugin) =>
                  filteredRows.some((row) => row.tool_id === plugin.tool_id),
                ),
        }))
        .filter(
          (group) =>
            group.plugins.length > 0 ||
            (searchQuery.trim() === "" && statusFilter === "all"),
        ),
    [currentGroups, filteredRows],
  );
  const visibleGroup = useMemo(
    () =>
      selectedFeatureCode === null
        ? null
        : filteredGroups.find((group) => group.feature_code === selectedFeatureCode) ?? null,
    [filteredGroups, selectedFeatureCode],
  );
  const text = pluginManagementCopy[locale];
  const inlineSeparator = locale === "zh-CN" ? "，" : ", ";

  const requestForceEnable = async (
    pluginId: string,
    supportsMultiplePlugins: boolean,
    activePluginIds: string[],
  ) => {
    const conflictingActivePluginIds = activePluginIds.filter((activeId) => activeId !== pluginId);
    if (!supportsMultiplePlugins && conflictingActivePluginIds.length > 0) {
      setForceEnableAuditReason("");
      setPendingForceEnable({
        pluginId,
        activePluginIds: conflictingActivePluginIds,
      });
      return;
    }
    await runPluginAction(pluginId, "force-enable");
  };

  return (
    <Stack spacing={3}>
      <Stack
        direction={{ xs: "column", md: "row" }}
        justifyContent="space-between"
        alignItems={{ xs: "flex-start", md: "center" }}
        spacing={2}
      >
        <Box>
          <Typography variant="h4" component="h1" gutterBottom>
            {t("plugins.title")}
          </Typography>
          <Typography variant="body1" color="text.secondary">
            {t("plugins.subtitle")}
          </Typography>
        </Box>
        <Stack direction="row" spacing={2}>
          <FormControl sx={{ minWidth: 140 }}>
            <InputLabel id="plugin-language-label">{t("common.language")}</InputLabel>
            <Select
              labelId="plugin-language-label"
              value={locale}
              label={t("common.language")}
              onChange={(event) => {
                const newLang = event.target.value as Locale;
                setLocale(newLang);
                i18n.changeLanguage(newLang);
              }}
            >
              <MenuItem value="zh-CN">中文</MenuItem>
              <MenuItem value="en-US">English</MenuItem>
            </Select>
          </FormControl>
          <Button variant="contained" onClick={() => void loadPlugins()} disabled={loading}>
            {loading ? t("common.refreshing") : t("common.refresh")}
          </Button>
        </Stack>
      </Stack>

      <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
        <TextField
          label={t("plugins.search")}
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          fullWidth
        />
        <FormControl sx={{ minWidth: { xs: "100%", md: 220 } }}>
          <InputLabel id="plugin-status-filter-label">{t("plugins.statusFilter")}</InputLabel>
          <Select
            labelId="plugin-status-filter-label"
            value={statusFilter}
            label={t("plugins.statusFilter")}
            onChange={(event) =>
              setStatusFilter(event.target.value as "all" | CognitivePluginRow["status"])
            }
          >
            <MenuItem value="all">{t("plugins.allStatuses")}</MenuItem>
            <MenuItem value="candidate">{formatPluginStatus("candidate", locale)}</MenuItem>
            <MenuItem value="sandbox_verified">{formatPluginStatus("sandbox_verified", locale)}</MenuItem>
            <MenuItem value="active">{formatPluginStatus("active", locale)}</MenuItem>
            <MenuItem value="degraded">{formatPluginStatus("degraded", locale)}</MenuItem>
            <MenuItem value="revoked">{formatPluginStatus("revoked", locale)}</MenuItem>
          </Select>
        </FormControl>
        <FormControl sx={{ minWidth: { xs: "100%", md: 180 } }}>
          <InputLabel id="plugin-refresh-interval-label">{t("plugins.interval")}</InputLabel>
          <Select
            labelId="plugin-refresh-interval-label"
            value={refreshIntervalMs}
            label={t("plugins.interval")}
            onChange={(event) =>
              setRefreshIntervalMs(event.target.value as 10000 | 30000 | 60000)
            }
          >
            <MenuItem value={10000}>10s</MenuItem>
            <MenuItem value={30000}>30s</MenuItem>
            <MenuItem value={60000}>60s</MenuItem>
          </Select>
        </FormControl>
        <FormControlLabel
          control={
            <Switch
              checked={autoRefreshEnabled}
              onChange={(event) => setAutoRefreshEnabled(event.target.checked)}
            />
          }
          label={t("plugins.autoRefresh")}
        />
      </Stack>

      <Box sx={{ borderBottom: 1, borderColor: "divider" }}>
        <Tabs
          value={activeTab}
          onChange={(_event: React.SyntheticEvent, newValue: "cognitive" | "functional") => {
            setActiveTab(newValue);
            setSelectedFeatureCode(null);
          }}
          aria-label="plugin type tabs"
        >
          <Tab label={t("plugins.cognitivePlugins")} value="cognitive" />
          <Tab label={t("plugins.functionalPlugins")} value="functional" />
        </Tabs>
      </Box>

      {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}
      {actionMessage ? <Alert severity="info">{actionMessage}</Alert> : null}

      {alertRows.length > 0 ? (
        <Alert severity="warning">
          {t("plugins.alertPrefix")}
          {alertRows.map((row) => `${row.tool_id} (${formatPluginStatus(row.status, locale)})`).join(inlineSeparator)}
        </Alert>
      ) : null}

      {loading ? (
        <Paper variant="outlined">
          <Stack alignItems="center" justifyContent="center" sx={{ py: 8 }}>
            <CircularProgress />
          </Stack>
        </Paper>
      ) : selectedFeatureCode === null ? (
        <Paper variant="outlined">
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>{t("plugins.featureFamily")}</TableCell>
                  <TableCell>{t("plugins.featureBindingStatus")}</TableCell>
                  <TableCell>{t("plugins.activePlugins")}</TableCell>
                  <TableCell>{t("plugins.featureGuides")}</TableCell>
                  <TableCell align="right">{t("plugins.version")}</TableCell>
                  <TableCell align="right">{t("plugins.actions")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredGroups.map((group) => (
                  <TableRow
                    key={group.feature_code}
                    hover
                    sx={{
                      cursor: "pointer",
                    }}
                  >
                    <TableCell>
                      <Typography variant="subtitle2">{group.display_name}</Typography>
                      <Typography variant="body2" color="text.secondary">
                        {group.feature_code}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        <Chip
                          size="small"
                          color={getBindingStatusColor(group.binding_status)}
                          label={formatPluginBindingStatus(group.binding_status, locale)}
                        />
                        <Chip
                          size="small"
                          variant="outlined"
                          label={
                            group.supports_multiple_plugins
                              ? t("plugins.multiPluginMode")
                              : t("plugins.singlePluginMode")
                          }
                        />
                      </Stack>
                    </TableCell>
                    <TableCell>
                      {group.active_plugin_ids.length > 0
                        ? group.active_plugin_ids.join(inlineSeparator)
                        : "--"}
                    </TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        {group.feature_guide_path ? (
                          <Button
                            size="small"
                            variant="text"
                            href={group.feature_guide_path}
                            target="_blank"
                            rel="noreferrer"
                            onClick={(event) => event.stopPropagation()}
                          >
                            {t("plugins.featureGuide")}
                          </Button>
                        ) : null}
                        {group.family_guide_path ? (
                          <Button
                            size="small"
                            variant="text"
                            href={group.family_guide_path}
                            target="_blank"
                            rel="noreferrer"
                            onClick={(event) => event.stopPropagation()}
                          >
                            {t("plugins.familyGuide")}
                          </Button>
                        ) : null}
                      </Stack>
                    </TableCell>
                    <TableCell align="right">
                      <Chip
                        size="small"
                        label={group.plugins[0]?.version ?? "--"}
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell align="right">
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={(event) => {
                          event.stopPropagation();
                          setSelectedFeatureCode(group.feature_code);
                        }}
                      >
                        {t("plugins.viewVersions")}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {filteredGroups.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6}>
                      <Typography variant="body2" color="text.secondary" sx={{ py: 4 }}>
                        {text.empty}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      ) : visibleGroup ? (
        <Stack spacing={3}>
          <Button
            startIcon={<span>&larr;</span>}
            onClick={() => setSelectedFeatureCode(null)}
          >
            {t("plugins.backToFeatures")}
          </Button>

          <Paper variant="outlined">
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>{t("plugins.toolId")}</TableCell>
                    <TableCell>{t("plugins.version")}</TableCell>
                    <TableCell>{t("plugins.usedIn")}</TableCell>
                    <TableCell>{t("plugins.lifecycleStatus")}</TableCell>
                    <TableCell align="right">{t("plugins.usageCount")}</TableCell>
                    <TableCell align="right">{t("plugins.failureCount")}</TableCell>
                    <TableCell align="right">{t("plugins.actions")}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {visibleGroup.plugins.map((row) => (
                    <TableRow
                      key={row.tool_id}
                      hover
                      onClick={() => setSelectedPlugin(row)}
                      sx={{ cursor: "pointer" }}
                    >
                      <TableCell>
                        <Typography variant="subtitle2">{row.tool_id}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          {row.plugin_kind}
                        </Typography>
                      </TableCell>
                      <TableCell>{row.version}</TableCell>
                      <TableCell>
                        {row.used_in.length > 0
                          ? row.used_in.map((usage) => formatPluginDescriptor(usage, locale)).join(inlineSeparator)
                          : text.noUsedIn}
                      </TableCell>
                      <TableCell>
                        <Chip
                          size="small"
                          label={formatPluginStatus(row.status, locale)}
                          color={getStatusColor(row.status)}
                          variant="outlined"
                        />
                      </TableCell>
                      <TableCell align="right">{row.usage_count}</TableCell>
                      <TableCell align="right">{row.failure_count}</TableCell>
                      <TableCell align="right">
                        <Stack direction="row" spacing={1} justifyContent="flex-end">
                          {row.can_force_enable && !row.is_default ? (
                            <Button
                              size="small"
                              variant="outlined"
                              color="success"
                              title={text.officialOnlyHint}
                              onClick={(event) => {
                                event.stopPropagation();
                                void requestForceEnable(
                                  row.tool_id,
                                  row.supports_multiple_plugins,
                                  visibleGroup.active_plugin_ids,
                                );
                              }}
                            >
                              {t("plugins.forceEnable")}
                            </Button>
                          ) : null}
                          {row.can_force_disable ? (
                            <Button
                              size="small"
                              variant="outlined"
                              color="warning"
                              title={text.forceDisableHint}
                              onClick={(event) => {
                                event.stopPropagation();
                                void runPluginAction(row.tool_id, "force-disable");
                              }}
                            >
                              {t("plugins.forceDisable")}
                            </Button>
                          ) : null}
                          {row.can_delete && !row.is_default ? (
                            <Button
                              size="small"
                              variant="outlined"
                              color="error"
                              title={row.status === "active" ? text.deleteEnabledHint : text.protectedDeleteHint}
                              disabled={row.status === "active"}
                              onClick={(event) => {
                                event.stopPropagation();
                                void runPluginAction(row.tool_id, "delete");
                              }}
                            >
                              {t("plugins.deletePlugin")}
                            </Button>
                          ) : null}
                        </Stack>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </Stack>
      ) : null}

      {selectedPlugin ? (
        <Drawer
          anchor="right"
          open={!!selectedPlugin}
          onClose={() => setSelectedPlugin(null)}
          sx={{ width: 400 }}
          PaperProps={{ sx: { width: 400, p: 3 } }}
        >
          <Stack spacing={2}>
            <Typography variant="h6">{selectedPlugin.tool_id}</Typography>
            <Typography variant="body2" color="text.secondary">
              {selectedPlugin.plugin_kind} · v{selectedPlugin.version}
            </Typography>
            <Divider />
            <Typography variant="subtitle2">{t("plugins.description")}</Typography>
            <Typography variant="body2">{selectedPlugin.description}</Typography>
            <Typography variant="subtitle2">{t("plugins.purpose")}</Typography>
            <Typography variant="body2">{selectedPlugin.purpose || text.noPurpose}</Typography>
            <Typography variant="subtitle2">{t("plugins.lifecycleTimes")}</Typography>
            <List dense>
              <ListItem>
                <ListItemText primary={t("plugins.createdAt")} secondary={formatLocalizedDateTime(selectedPlugin.created_at, locale)} />
              </ListItem>
              <ListItem>
                <ListItemText primary={t("plugins.updatedAt")} secondary={formatLocalizedDateTime(selectedPlugin.updated_at, locale)} />
              </ListItem>
              <ListItem>
                <ListItemText primary={t("plugins.startedAt")} secondary={formatLocalizedDateTime(selectedPlugin.started_at, locale)} />
              </ListItem>
              <ListItem>
                <ListItemText primary={t("plugins.stoppedAt")} secondary={formatLocalizedDateTime(selectedPlugin.stopped_at, locale)} />
              </ListItem>
              <ListItem>
                <ListItemText primary={t("plugins.lastUsedAt")} secondary={formatLocalizedDateTime(selectedPlugin.last_used_at, locale)} />
              </ListItem>
            </List>
            <Typography variant="subtitle2">{t("plugins.rollbackConditions")}</Typography>
            <Typography variant="body2">
              {selectedPlugin.rollback_conditions.length > 0
                ? selectedPlugin.rollback_conditions.join(inlineSeparator)
                : text.noRollbackConditions}
            </Typography>
            <Typography variant="subtitle2">{t("plugins.triggerConditions")}</Typography>
            <Typography variant="body2">
              {selectedPlugin.trigger_conditions.length > 0
                ? selectedPlugin.trigger_conditions.join(inlineSeparator)
                : text.noTriggerConditions}
            </Typography>
            <Typography variant="subtitle2">{t("plugins.requiredContext")}</Typography>
            <Typography variant="body2">
              {selectedPlugin.required_context.length > 0
                ? selectedPlugin.required_context.join(inlineSeparator)
                : text.noRequiredContext}
            </Typography>
          </Stack>
        </Drawer>
      ) : null}

      <Dialog
        open={!!pendingForceEnable}
        onClose={() => setPendingForceEnable(null)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>{t("plugins.overrideDialogTitle")}</DialogTitle>
        <DialogContent>
          <Typography variant="body1" sx={{ mb: 2 }}>
            {t("plugins.overrideDialogBody")}
          </Typography>
          <Typography variant="subtitle2" color="text.secondary">
            {t("plugins.overrideDialogActiveLabel")}
          </Typography>
          <List dense>
            {pendingForceEnable?.activePluginIds.map((id) => (
              <ListItem key={id}>
                <ListItemText primary={id} />
              </ListItem>
            ))}
          </List>
          <TextField
            autoFocus
            margin="dense"
            label={t("plugins.auditReasonPrompt")}
            fullWidth
            variant="outlined"
            value={forceEnableAuditReason}
            onChange={(event) => setForceEnableAuditReason(event.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPendingForceEnable(null)}>{t("common.cancel")}</Button>
          <Button
            onClick={() => {
              if (pendingForceEnable && forceEnableAuditReason.trim()) {
                void runPluginAction(pendingForceEnable.pluginId, "force-enable", forceEnableAuditReason);
                setPendingForceEnable(null);
                setForceEnableAuditReason("");
              }
            }}
            variant="contained"
            disabled={!forceEnableAuditReason.trim()}
          >
            {t("plugins.continueAction")}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
