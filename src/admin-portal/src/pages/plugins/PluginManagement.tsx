import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Switch,
  Tab,
  Tabs,
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
  formatPluginOperationalStatus,
  formatPluginStatus,
  pluginManagementCopy,
  type Locale,
  type PluginOperationalStatus,
} from "../../i18n";
import {
  fetchCognitivePlugins,
  fetchFunctionalPlugins,
  forceDisablePlugin,
  forceEnablePlugin,
  type PluginRow,
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

function PluginTable({
  rows,
  emptyText,
  locale,
  onOpenDetail,
  onForceEnable,
  onForceDisable,
  actionLoadingToolId,
  showLifecycleActions = true,
}: {
  rows: PluginRow[];
  emptyText: string;
  locale: Locale;
  onOpenDetail: (plugin: PluginRow) => void;
  onForceEnable: (plugin: PluginRow) => void;
  onForceDisable: (plugin: PluginRow) => void;
  actionLoadingToolId: string | null;
  showLifecycleActions?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <Paper variant="outlined">
      <TableContainer>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>{t("plugins.toolId")}</TableCell>
              <TableCell>{t("plugins.version")}</TableCell>
              <TableCell>{t("plugins.lifecycleStatus")}</TableCell>
              <TableCell>{t("plugins.status")}</TableCell>
              <TableCell>{t("plugins.description")}</TableCell>
              <TableCell align="right">{t("plugins.usageCount")}</TableCell>
              <TableCell align="right">{t("plugins.failureCount")}</TableCell>
              <TableCell align="right">{t("plugins.actions")}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.tool_id} hover sx={{ cursor: "pointer" }} onClick={() => onOpenDetail(row)}>
                <TableCell>
                  <Typography variant="subtitle2">{row.tool_id}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {row.feature_code}
                  </Typography>
                </TableCell>
                <TableCell>{row.version}</TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    color={getStatusColor(row.lifecycle_status)}
                    label={formatPluginStatus(row.lifecycle_status, locale)}
                    variant="outlined"
                  />
                </TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    color={getOperationalStatusColor(row.operational_status)}
                    label={formatPluginOperationalStatus(row.operational_status, locale)}
                    variant="outlined"
                  />
                </TableCell>
                <TableCell>
                  <Typography variant="body2" noWrap sx={{ maxWidth: 340 }}>
                    {row.description}
                  </Typography>
                </TableCell>
                <TableCell align="right">{row.usage_count}</TableCell>
                <TableCell align="right">{row.failure_count}</TableCell>
                <TableCell align="right">
                  <Stack direction="row" spacing={1} justifyContent="flex-end">
                    <Button size="small" variant="outlined" onClick={(event) => {
                      event.stopPropagation();
                      onOpenDetail(row);
                    }}>
                      {locale === "zh-CN" ? "查看" : "View"}
                    </Button>
                    {showLifecycleActions ? (
                      <>
                        <Button
                          size="small"
                          variant="contained"
                          disabled={!row.can_force_enable || actionLoadingToolId === row.tool_id}
                          onClick={(event) => {
                            event.stopPropagation();
                            onForceEnable(row);
                          }}
                        >
                          {pluginManagementCopy[locale].forceEnable}
                        </Button>
                        <Button
                          size="small"
                          color="warning"
                          variant="outlined"
                          disabled={!row.can_force_disable || actionLoadingToolId === row.tool_id}
                          onClick={(event) => {
                            event.stopPropagation();
                            onForceDisable(row);
                          }}
                        >
                          {pluginManagementCopy[locale].forceDisable}
                        </Button>
                      </>
                    ) : null}
                  </Stack>
                </TableCell>
              </TableRow>
            ))}
            {rows.length === 0 ? (
              <TableRow>
                  <TableCell colSpan={8}>
                  <Typography variant="body2" color="text.secondary" sx={{ py: 4 }}>
                    {emptyText}
                  </Typography>
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
}

export default function PluginManagement() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [locale, setLocale] = useState<Locale>((i18n.language as Locale) || "zh-CN");
  const [activeTab, setActiveTab] = useState<"cognitive" | "functional">("cognitive");
  const [cognitiveRows, setCognitiveRows] = useState<PluginRow[]>([]);
  const [functionalRows, setFunctionalRows] = useState<PluginRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | PluginOperationalStatus>("all");
  const [actionLoadingToolId, setActionLoadingToolId] = useState<string | null>(null);

  const text = pluginManagementCopy[locale];

  const loadPlugins = async () => {
    setLoading(true);
    try {
      const [cognitive, functional] = await Promise.all([
        fetchCognitivePlugins(),
        fetchFunctionalPlugins(),
      ]);
      setCognitiveRows(cognitive);
      setFunctionalRows(functional);
      setErrorMessage(null);
    } catch {
      setErrorMessage(text.backendError);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadPlugins();
  }, []);

  const currentRows = activeTab === "cognitive" ? cognitiveRows : functionalRows;

  const filteredRows = useMemo(
    () =>
      currentRows.filter((row) => {
        const matchesSearch =
          searchQuery.trim() === "" ||
          row.tool_id.toLowerCase().includes(searchQuery.trim().toLowerCase()) ||
          row.feature_code.toLowerCase().includes(searchQuery.trim().toLowerCase());
        const matchesStatus = statusFilter === "all" || row.operational_status === statusFilter;
        return matchesSearch && matchesStatus;
      }),
    [currentRows, searchQuery, statusFilter],
  );

  const openDetail = (plugin: PluginRow) => {
    navigate(`/console/plugins/${activeTab}/${encodeURIComponent(plugin.tool_id)}`);
  };

  const handleForceEnable = async (plugin: PluginRow) => {
    const reason = window.prompt(pluginManagementCopy[locale].auditReasonPrompt);
    if (!reason || !reason.trim()) {
      return;
    }
    setActionLoadingToolId(plugin.tool_id);
    try {
      await forceEnablePlugin(plugin.tool_id, reason.trim());
      await loadPlugins();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : pluginManagementCopy[locale].actionFailed);
    } finally {
      setActionLoadingToolId(null);
    }
  };

  const handleForceDisable = async (plugin: PluginRow) => {
    const reason = window.prompt(pluginManagementCopy[locale].auditReasonPrompt);
    if (!reason || !reason.trim()) {
      return;
    }
    setActionLoadingToolId(plugin.tool_id);
    try {
      await forceDisablePlugin(plugin.tool_id, reason.trim());
      await loadPlugins();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : pluginManagementCopy[locale].actionFailed);
    } finally {
      setActionLoadingToolId(null);
    }
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
            onChange={(event) => setStatusFilter(event.target.value as "all" | PluginOperationalStatus)}
          >
            <MenuItem value="all">{t("plugins.allStatuses")}</MenuItem>
                <MenuItem value="enabled">{formatPluginOperationalStatus("enabled", locale)}</MenuItem>
                <MenuItem value="stopped">{formatPluginOperationalStatus("stopped", locale)}</MenuItem>
                <MenuItem value="abnormal">{formatPluginOperationalStatus("abnormal", locale)}</MenuItem>
                <MenuItem value="unavailable">{formatPluginOperationalStatus("unavailable", locale)}</MenuItem>
              </Select>
            </FormControl>
      </Stack>

      <Box sx={{ borderBottom: 1, borderColor: "divider" }}>
        <Tabs
          value={activeTab}
          onChange={(_event: React.SyntheticEvent, newValue: "cognitive" | "functional") => {
            setActiveTab(newValue);
          }}
          aria-label="plugin type tabs"
        >
          <Tab label={`${t("plugins.cognitivePlugins")} (${cognitiveRows.length})`} value="cognitive" />
          <Tab label={`${t("plugins.functionalPlugins")} (${functionalRows.length})`} value="functional" />
        </Tabs>
      </Box>

      {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}

      {loading ? (
        <Paper variant="outlined">
          <Stack alignItems="center" justifyContent="center" sx={{ py: 8 }}>
            <CircularProgress />
          </Stack>
        </Paper>
      ) : activeTab === "cognitive" ? (
            <PluginTable
              rows={filteredRows}
          emptyText={text.empty}
          locale={locale}
          onOpenDetail={openDetail}
          onForceEnable={handleForceEnable}
          onForceDisable={handleForceDisable}
          actionLoadingToolId={actionLoadingToolId}
          showLifecycleActions={false}
        />
      ) : (
        <PluginTable
          rows={filteredRows}
          emptyText={text.functionalEmpty}
          locale={locale}
          onOpenDetail={openDetail}
          onForceEnable={handleForceEnable}
          onForceDisable={handleForceDisable}
          actionLoadingToolId={actionLoadingToolId}
        />
      )}

      {activeTab === "cognitive" && filteredRows.length > 0 ? (
        <Typography variant="body2" color="text.secondary">
          {t("plugins.cognitivePlugins")}: {filteredRows.length}
        </Typography>
      ) : null}
      {activeTab === "functional" && filteredRows.length > 0 ? (
        <Typography variant="body2" color="text.secondary">
          {t("plugins.functionalPlugins")}: {filteredRows.length}
        </Typography>
      ) : null}

    </Stack>
  );
}
