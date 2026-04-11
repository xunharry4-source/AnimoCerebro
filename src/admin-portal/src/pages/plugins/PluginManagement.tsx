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
import { formatPluginStatus, pluginManagementCopy, type Locale } from "../../i18n";
import {
  fetchCognitivePlugins,
  fetchFunctionalPlugins,
  type PluginRow,
} from "./pluginsApi";

function getStatusColor(
  status: PluginRow["status"],
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

function PluginTable({
  rows,
  emptyText,
  locale,
  onOpenDetail,
}: {
  rows: PluginRow[];
  emptyText: string;
  locale: Locale;
  onOpenDetail: (plugin: PluginRow) => void;
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
                    color={getStatusColor(row.status)}
                    label={formatPluginStatus(row.status, locale)}
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
                  <Button size="small" variant="outlined" onClick={(event) => {
                    event.stopPropagation();
                    onOpenDetail(row);
                  }}>
                    {locale === "zh-CN" ? "查看" : "View"}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7}>
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
  const [statusFilter, setStatusFilter] = useState<"all" | PluginRow["status"]>("all");
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
  const [refreshIntervalMs, setRefreshIntervalMs] = useState<10000 | 30000 | 60000>(10000);

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

  useEffect(() => {
    if (!autoRefreshEnabled) {
      return undefined;
    }
    const timerId = window.setInterval(() => {
      void loadPlugins();
    }, refreshIntervalMs);
    return () => window.clearInterval(timerId);
  }, [autoRefreshEnabled, refreshIntervalMs]);

  const currentRows = activeTab === "cognitive" ? cognitiveRows : functionalRows;

  const filteredRows = useMemo(
    () =>
      currentRows.filter((row) => {
        const matchesSearch =
          searchQuery.trim() === "" ||
          row.tool_id.toLowerCase().includes(searchQuery.trim().toLowerCase()) ||
          row.feature_code.toLowerCase().includes(searchQuery.trim().toLowerCase());
        const matchesStatus = statusFilter === "all" || row.status === statusFilter;
        return matchesSearch && matchesStatus;
      }),
    [currentRows, searchQuery, statusFilter],
  );

  const openDetail = (plugin: PluginRow) => {
    navigate(`/console/plugins/${activeTab}/${encodeURIComponent(plugin.tool_id)}`);
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
            onChange={(event) => setStatusFilter(event.target.value as "all" | PluginRow["status"])}
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
            onChange={(event) => setRefreshIntervalMs(event.target.value as 10000 | 30000 | 60000)}
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
        />
      ) : (
        <PluginTable
          rows={filteredRows}
          emptyText={text.functionalEmpty}
          locale={locale}
          onOpenDetail={openDetail}
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
