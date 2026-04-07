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
  const [locale, setLocale] = useState<Locale>("zh-CN");
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

  const alertRows = useMemo(
    () => rows.filter((row) => row.status === "degraded" || row.status === "revoked"),
    [rows],
  );
  const filteredGroups = useMemo(
    () =>
      groups
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
    [filteredRows, groups],
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
            {text.title}
          </Typography>
          <Typography variant="body1" color="text.secondary">
            {text.subtitle}
          </Typography>
        </Box>
        <Stack direction="row" spacing={2}>
          <FormControl sx={{ minWidth: 140 }}>
            <InputLabel id="plugin-language-label">{text.language}</InputLabel>
            <Select
              labelId="plugin-language-label"
              value={locale}
              label={text.language}
              onChange={(event) => setLocale(event.target.value as Locale)}
            >
              <MenuItem value="zh-CN">中文</MenuItem>
              <MenuItem value="en-US">English</MenuItem>
            </Select>
          </FormControl>
          <Button variant="contained" onClick={() => void loadPlugins()} disabled={loading}>
            {loading ? text.refreshing : text.refresh}
          </Button>
        </Stack>
      </Stack>

      <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
        <TextField
          label={text.search}
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          fullWidth
        />
        <FormControl sx={{ minWidth: { xs: "100%", md: 220 } }}>
          <InputLabel id="plugin-status-filter-label">{text.statusFilter}</InputLabel>
          <Select
            labelId="plugin-status-filter-label"
            value={statusFilter}
            label={text.statusFilter}
            onChange={(event) =>
              setStatusFilter(event.target.value as "all" | CognitivePluginRow["status"])
            }
          >
            <MenuItem value="all">{text.allStatuses}</MenuItem>
            <MenuItem value="candidate">{formatPluginStatus("candidate", locale)}</MenuItem>
            <MenuItem value="sandbox_verified">{formatPluginStatus("sandbox_verified", locale)}</MenuItem>
            <MenuItem value="active">{formatPluginStatus("active", locale)}</MenuItem>
            <MenuItem value="degraded">{formatPluginStatus("degraded", locale)}</MenuItem>
            <MenuItem value="revoked">{formatPluginStatus("revoked", locale)}</MenuItem>
          </Select>
        </FormControl>
        <FormControl sx={{ minWidth: { xs: "100%", md: 180 } }}>
          <InputLabel id="plugin-refresh-interval-label">{text.interval}</InputLabel>
          <Select
            labelId="plugin-refresh-interval-label"
            value={refreshIntervalMs}
            label={text.interval}
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
          label={text.autoRefresh}
        />
      </Stack>

      {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}
      {actionMessage ? <Alert severity="info">{actionMessage}</Alert> : null}

      {alertRows.length > 0 ? (
        <Alert severity="warning">
          {text.alertPrefix}
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
                  <TableCell>{text.featureFamily}</TableCell>
                  <TableCell>{text.featureBindingStatus}</TableCell>
                  <TableCell>{text.activePlugins}</TableCell>
                  <TableCell>{text.featureGuides}</TableCell>
                  <TableCell align="right">{text.version}</TableCell>
                  <TableCell align="right">{text.actions}</TableCell>
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
                              ? text.multiPluginMode
                              : text.singlePluginMode
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
                            {text.featureGuide}
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
                            {text.familyGuide}
                          </Button>
                        ) : null}
                        {!group.feature_guide_path && !group.family_guide_path ? "--" : null}
                      </Stack>
                    </TableCell>
                    <TableCell align="right">
                      {group.plugins.length}
                    </TableCell>
                    <TableCell align="right">
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() => setSelectedFeatureCode(group.feature_code)}
                      >
                        {text.viewVersions}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      ) : visibleGroup ? (
        <Paper variant="outlined">
          <Stack
            direction={{ xs: "column", md: "row" }}
            justifyContent="space-between"
            spacing={2}
            sx={{ px: 2, py: 2 }}
          >
            <Box>
                <Button
                  size="small"
                  variant="text"
                  onClick={() => setSelectedFeatureCode(null)}
                  sx={{ mb: 1, px: 0 }}
                >
                {text.backToFeatures}
                </Button>
              <Typography variant="subtitle1">{visibleGroup.display_name}</Typography>
              <Typography variant="body2" color="text.secondary">
                {visibleGroup.feature_code}
              </Typography>
            </Box>
            <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ md: "center" }}>
              <Chip
                color={getBindingStatusColor(visibleGroup.binding_status)}
                label={formatPluginBindingStatus(visibleGroup.binding_status, locale)}
              />
              <Chip
                size="small"
                variant="outlined"
                label={
                  visibleGroup.supports_multiple_plugins
                    ? text.multiPluginMode
                    : text.singlePluginMode
                }
              />
              <Typography variant="body2" color="text.secondary">
                {text.activePlugins}: {visibleGroup.active_plugin_ids.length > 0 ? visibleGroup.active_plugin_ids.join(inlineSeparator) : "--"}
              </Typography>
              {visibleGroup.feature_guide_path ? (
                <Button
                  size="small"
                  variant="outlined"
                  href={visibleGroup.feature_guide_path}
                  target="_blank"
                  rel="noreferrer"
                >
                  {text.featureGuide}
                </Button>
              ) : null}
              {visibleGroup.family_guide_path ? (
                <Button
                  size="small"
                  variant="outlined"
                  href={visibleGroup.family_guide_path}
                  target="_blank"
                  rel="noreferrer"
                >
                  {text.familyGuide}
                </Button>
              ) : null}
            </Stack>
          </Stack>
          {visibleGroup.binding_status === "unbound" ? (
            <Alert severity="warning" sx={{ mx: 2, mb: 2 }}>
              {text.noBoundPlugin}
            </Alert>
          ) : null}
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>{text.toolId}</TableCell>
                  <TableCell>{text.version}</TableCell>
                  <TableCell>{text.usedIn}</TableCell>
                  <TableCell>{text.description}</TableCell>
                  <TableCell>{text.status}</TableCell>
                  <TableCell align="right">{text.usageCount}</TableCell>
                  <TableCell align="right">{text.failureCount}</TableCell>
                  <TableCell align="right">{text.actions}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {visibleGroup.plugins.length > 0 ? visibleGroup.plugins.map((row) => (
                  <TableRow
                    key={row.tool_id}
                    hover
                    onClick={() => setSelectedPlugin(row)}
                    sx={{
                      cursor: "pointer",
                      backgroundColor:
                        row.failure_count >= 3 ? "rgba(255, 244, 229, 0.8)" : "inherit",
                    }}
                  >
                    <TableCell>{row.tool_id}</TableCell>
                    <TableCell>{row.version}</TableCell>
                    <TableCell>
                      {row.used_in.length > 0
                        ? row.used_in.map((item) => formatPluginDescriptor(item, locale)).join(" / ")
                        : "--"}
                    </TableCell>
                    <TableCell>{row.description}</TableCell>
                    <TableCell>
                      <Chip
                        label={formatPluginStatus(row.status, locale)}
                        color={getStatusColor(row.status)}
                        size="small"
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell align="right">{row.usage_count}</TableCell>
                    <TableCell align="right">
                      <Chip
                        label={row.failure_count}
                        color={row.failure_count >= 3 ? "warning" : "default"}
                        size="small"
                        variant={row.failure_count >= 3 ? "filled" : "outlined"}
                      />
                    </TableCell>
                    <TableCell align="right">
                      <Stack direction="row" spacing={1} justifyContent="flex-end">
                        <Button
                          size="small"
                          variant="outlined"
                          disabled={!row.can_force_enable}
                          title={row.can_force_enable ? undefined : text.officialOnlyHint}
                          onClick={(event) => {
                            event.stopPropagation();
                            void requestForceEnable(
                              row.tool_id,
                              row.supports_multiple_plugins,
                              visibleGroup.active_plugin_ids,
                            );
                          }}
                        >
                          {text.forceEnable}
                        </Button>
                        <Button
                          size="small"
                          color="warning"
                          variant="outlined"
                          disabled={!row.can_force_disable}
                          title={row.can_force_disable ? undefined : text.forceDisableHint}
                          onClick={(event) => {
                            event.stopPropagation();
                            void runPluginAction(row.tool_id, "force-disable");
                          }}
                        >
                          {text.forceDisable}
                        </Button>
                        <Button
                          size="small"
                          color="error"
                          variant="outlined"
                          disabled={!row.can_delete}
                          title={
                            row.is_default
                              ? text.protectedDeleteHint
                              : row.status === "active"
                                ? text.deleteEnabledHint
                                : undefined
                          }
                          onClick={(event) => {
                            event.stopPropagation();
                            void runPluginAction(row.tool_id, "delete");
                          }}
                        >
                          {text.deletePlugin}
                        </Button>
                      </Stack>
                    </TableCell>
                  </TableRow>
                )) : (
                  <TableRow>
                    <TableCell colSpan={8}>
                      <Typography variant="body2" color="text.secondary">
                        {text.noVersions}
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      ) : (
        <Paper variant="outlined">
          <Box sx={{ py: 4, textAlign: "center" }}>
            <Typography variant="body2" color="text.secondary">
              {text.empty}
            </Typography>
          </Box>
        </Paper>
      )}

      <Drawer
        anchor="right"
        open={selectedPlugin !== null}
        onClose={() => setSelectedPlugin(null)}
      >
        <Box sx={{ width: { xs: 320, sm: 420 }, p: 3 }}>
          {selectedPlugin ? (
            <Stack spacing={3}>
              <Box>
                <Typography variant="h5" gutterBottom>
                  {selectedPlugin.tool_id}
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  <Chip
                    label={formatPluginStatus(selectedPlugin.status, locale)}
                    color={getStatusColor(selectedPlugin.status)}
                    size="small"
                    variant="outlined"
                  />
                  <Chip label={`v${selectedPlugin.version}`} size="small" variant="outlined" />
                  <Chip
                    label={formatHealthStatus(selectedPlugin.health_status, locale)}
                    size="small"
                    variant="outlined"
                  />
                </Stack>
              </Box>

              <Divider />

              <Box>
                <Typography variant="subtitle1" gutterBottom>
                  {text.purpose}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {selectedPlugin.purpose || text.noPurpose}
                </Typography>
              </Box>

              <Divider />

              <Box>
                <Typography variant="subtitle1" gutterBottom>
                  {text.usedIn}
                </Typography>
                <List dense disablePadding>
                  {selectedPlugin.used_in.length > 0 ? (
                    selectedPlugin.used_in.map((item) => (
                      <ListItem key={item} disableGutters>
                        <ListItemText
                          primary={formatPluginDescriptor(item, locale)}
                          secondary={item}
                        />
                      </ListItem>
                    ))
                  ) : (
                    <ListItem disableGutters>
                      <ListItemText primary={text.noUsedIn} />
                    </ListItem>
                  )}
                </List>
              </Box>

              <Divider />

              <Box>
                <Typography variant="subtitle1" gutterBottom>
                  {text.lifecycleTimes}
                </Typography>
                <List dense disablePadding>
                  <ListItem disableGutters>
                    <ListItemText primary={text.createdAt} secondary={formatLocalizedDateTime(selectedPlugin.created_at, locale)} />
                  </ListItem>
                  <ListItem disableGutters>
                    <ListItemText primary={text.updatedAt} secondary={formatLocalizedDateTime(selectedPlugin.updated_at, locale)} />
                  </ListItem>
                  <ListItem disableGutters>
                    <ListItemText primary={text.startedAt} secondary={formatLocalizedDateTime(selectedPlugin.started_at, locale)} />
                  </ListItem>
                  <ListItem disableGutters>
                    <ListItemText primary={text.stoppedAt} secondary={formatLocalizedDateTime(selectedPlugin.stopped_at, locale)} />
                  </ListItem>
                  <ListItem disableGutters>
                    <ListItemText primary={text.lastUsedAt} secondary={formatLocalizedDateTime(selectedPlugin.last_used_at, locale)} />
                  </ListItem>
                </List>
              </Box>

              <Divider />

              <Box>
                <Typography variant="subtitle1" gutterBottom>
                  {text.rollbackConditions}
                </Typography>
                <List dense disablePadding>
                  {selectedPlugin.rollback_conditions.length > 0 ? (
                    selectedPlugin.rollback_conditions.map((condition) => (
                      <ListItem key={condition} disableGutters>
                        <ListItemText
                          primary={formatPluginDescriptor(condition, locale)}
                          secondary={condition}
                        />
                      </ListItem>
                    ))
                  ) : (
                    <ListItem disableGutters>
                      <ListItemText primary={text.noRollbackConditions} />
                    </ListItem>
                  )}
                </List>
              </Box>

              <Divider />

              <Box>
                <Typography variant="subtitle1" gutterBottom>
                  {text.triggerConditions}
                </Typography>
                <List dense disablePadding>
                  {selectedPlugin.trigger_conditions.length > 0 ? (
                    selectedPlugin.trigger_conditions.map((condition) => (
                      <ListItem key={condition} disableGutters>
                        <ListItemText
                          primary={formatPluginDescriptor(condition, locale)}
                          secondary={condition}
                        />
                      </ListItem>
                    ))
                  ) : (
                    <ListItem disableGutters>
                      <ListItemText primary={text.noTriggerConditions} />
                    </ListItem>
                  )}
                </List>
              </Box>

              <Divider />

              <Box>
                <Typography variant="subtitle1" gutterBottom>
                  {text.requiredContext}
                </Typography>
                <List dense disablePadding>
                  {selectedPlugin.required_context.length > 0 ? (
                    selectedPlugin.required_context.map((item) => (
                      <ListItem key={item} disableGutters>
                        <ListItemText
                          primary={formatPluginDescriptor(item, locale)}
                          secondary={item}
                        />
                      </ListItem>
                    ))
                  ) : (
                    <ListItem disableGutters>
                      <ListItemText primary={text.noRequiredContext} />
                    </ListItem>
                  )}
                </List>
              </Box>
            </Stack>
          ) : null}
        </Box>
      </Drawer>

      <Dialog
        open={pendingForceEnable !== null}
        onClose={() => {
          setPendingForceEnable(null);
          setForceEnableAuditReason("");
        }}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>{text.overrideDialogTitle}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <Alert severity="warning">{text.overrideDialogBody}</Alert>
            <Typography variant="body2" color="text.secondary">
              {text.overrideDialogActiveLabel}: {pendingForceEnable?.activePluginIds.join(inlineSeparator)}
            </Typography>
            <TextField
              label={text.auditReasonPrompt}
              value={forceEnableAuditReason}
              onChange={(event) => setForceEnableAuditReason(event.target.value)}
              fullWidth
              multiline
              minRows={3}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setPendingForceEnable(null);
              setForceEnableAuditReason("");
            }}
          >
            {text.cancel}
          </Button>
          <Button
            variant="contained"
            disabled={!forceEnableAuditReason.trim() || pendingForceEnable === null}
            onClick={() => {
              if (pendingForceEnable === null) {
                return;
              }
              const pluginId = pendingForceEnable.pluginId;
              const auditReason = forceEnableAuditReason.trim();
              setPendingForceEnable(null);
              setForceEnableAuditReason("");
              void runPluginAction(pluginId, "force-enable", auditReason);
            }}
          >
            {text.continueAction}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
