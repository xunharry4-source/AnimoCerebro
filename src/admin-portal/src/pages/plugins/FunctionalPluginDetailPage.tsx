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
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import HistoryIcon from "@mui/icons-material/History";
import {
  formatLocalizedDateTime,
  formatPluginOperationalStatus,
  formatPluginStatus,
  pluginManagementCopy,
  type Locale,
} from "../../i18n";
import {
  fetchFunctionalPluginDetail,
  type FunctionalPluginDetailResponse,
  type PluginRelationshipItem,
} from "./pluginsApi";

function getStatusColor(
  status: FunctionalPluginDetailResponse["plugin"]["lifecycle_status"],
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
  status: FunctionalPluginDetailResponse["plugin"]["operational_status"],
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
}: {
  history: FunctionalPluginDetailResponse["history"];
  locale: Locale;
}) {
  const { t } = useTranslation();
  if (history.length === 0) {
    return <Alert severity="info">{pluginManagementCopy[locale].noHistoryRecords}</Alert>;
  }

  return (
    <TableContainer component={Paper} variant="outlined">
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>{t("plugins.version")}</TableCell>
            <TableCell>{t("plugins.upgradeStatus")}</TableCell>
            <TableCell>{pluginManagementCopy[locale].startedAt}</TableCell>
            <TableCell>{pluginManagementCopy[locale].updatedAt}</TableCell>
            <TableCell>{pluginManagementCopy[locale].rollbackConditions}</TableCell>
            <TableCell>{pluginManagementCopy[locale].lastUsedAt}</TableCell>
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
              </TableCell>
              <TableCell>
                <Chip size="small" label={item.upgrade_status} variant="outlined" />
              </TableCell>
              <TableCell>{formatLocalizedDateTime(item.started_at, locale)}</TableCell>
              <TableCell>{formatLocalizedDateTime(item.completed_at, locale)}</TableCell>
              <TableCell>{item.error_message || "--"}</TableCell>
              <TableCell>{item.previous_version || "--"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function RelatedCognitiveTable({
  rows,
  locale,
  onOpen,
}: {
  rows: PluginRelationshipItem[];
  locale: Locale;
  onOpen: (pluginId: string) => void;
}) {
  const { t } = useTranslation();
  if (rows.length === 0) {
    return <Alert severity="info">{pluginManagementCopy[locale].noBoundCognitivePlugins}</Alert>;
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
                <Button size="small" variant="outlined" onClick={() => onOpen(row.plugin.tool_id)}>
                  {t("common.view")}
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

export default function FunctionalPluginDetailPage() {
  const { t, i18n } = useTranslation();
  const { pluginId } = useParams<{ pluginId: string }>();
  const navigate = useNavigate();
  const locale = (i18n.language as Locale) || "zh-CN";
  const [detail, setDetail] = useState<FunctionalPluginDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (pluginId) {
      void loadData(pluginId);
    }
  }, [pluginId]);

  const loadData = async (id: string) => {
    setLoading(true);
    try {
      const detailData = await fetchFunctionalPluginDetail(id);
      setDetail(detailData);
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "加载详情失败");
    } finally {
      setLoading(false);
    }
  };

  const refresh = async () => {
    if (pluginId) {
      await loadData(pluginId);
    }
  };

  const relatedCognitivePlugins = useMemo(() => detail?.cognitive_plugins ?? [], [detail]);

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
        <Button variant="outlined" onClick={() => void refresh()}>
          {t("common.refresh")}
        </Button>
      </Stack>

      {errorMessage ? <Alert severity="error" onClose={() => setErrorMessage(null)}>{errorMessage}</Alert> : null}

      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Chip label={detail.plugin.plugin_kind} variant="outlined" />
              <Chip label={detail.plugin.version} variant="outlined" />
              <Chip label={formatPluginStatus(detail.plugin.lifecycle_status, locale)} color={getStatusColor(detail.plugin.lifecycle_status)} />
              <Chip label={formatPluginOperationalStatus(detail.plugin.operational_status, locale)} color={getOperationalStatusColor(detail.plugin.operational_status)} />
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
              <HistoryIcon fontSize="small" />
              <Typography variant="h6">{pluginManagementCopy[locale].versionHistory}</Typography>
            </Stack>
            <HistoryTable history={detail.history} locale={locale} />
          </Stack>
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="h6">{pluginManagementCopy[locale].boundCognitivePlugins}</Typography>
            <RelatedCognitiveTable rows={relatedCognitivePlugins} locale={locale} onOpen={(id) => navigate(`/console/plugins/cognitive/${encodeURIComponent(id)}`)} />
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}
