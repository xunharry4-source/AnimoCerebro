/**
 * Upgrade management console for LLM optimization and plugin evolution jobs.
 *
 * This page displays upgrades in tabbed view by lifecycle status (ongoing, waiting,
 * failed, cancelled, completed) and allows navigation to detail pages.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Paper,
  Stack,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import ArticleIcon from "@mui/icons-material/Article";

import {
  cancelUpgradeRecord,
  cleanupFailedCandidate,
  fetchUpgradeOverview,
  fetchUpgradesByLifecycleView,
  type UpgradeOverviewPayload,
  type UpgradeRecordItem,
  type UpgradeTargetKind,
  type UpgradesByLifecycleViewPayload,
} from "./upgradesApi";

const TAB_LABELS = (t: (key: string) => string) => [
  { label: t("upgrades.tabOngoing"), value: "ongoing" },
  { label: t("upgrades.tabWaiting"), value: "waiting" },
  { label: t("upgrades.tabFailed"), value: "failed" },
  { label: t("upgrades.tabCancelled"), value: "cancelled" },
  { label: t("upgrades.tabCompleted"), value: "completed" },
];

function getLifecycleChipColor(
  value: string,
): "default" | "warning" | "info" | "success" | "error" {
  switch (value) {
    case "waiting":
    case "queued":
      return "warning";
    case "ongoing":
    case "planning":
    case "copying_source":
    case "scaffolding_candidate":
    case "running":
    case "validating":
    case "registered":
    case "active":
      return "info";
    case "completed":
    case "cleaned_up":
      return "success";
    case "failed":
    case "cancelled":
      return "error";
    default:
      return "default";
  }
}

function formatDateTime(value?: string | null): string {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export default function UpgradeManagement() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [targetKind, setTargetKind] = useState<UpgradeTargetKind>("llm");
  const [activeTab, setActiveTab] = useState(0);
  const [overview, setOverview] = useState<UpgradeOverviewPayload | null>(null);
  const [tabData, setTabData] = useState<UpgradesByLifecycleViewPayload | null>(null);
  const [loadingOverview, setLoadingOverview] = useState(true);
  const [loadingTabs, setLoadingTabs] = useState(true);
  const [actionLoadingRecordId, setActionLoadingRecordId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const loadOverview = async () => {
    setLoadingOverview(true);
    try {
      const payload = await fetchUpgradeOverview();
      setOverview(payload);
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : t("upgrades.overviewLoadFailed"));
    } finally {
      setLoadingOverview(false);
    }
  };

  const loadTabData = async () => {
    setLoadingTabs(true);
    try {
      const payload = await fetchUpgradesByLifecycleView(targetKind);
      setTabData(payload);
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : t("upgrades.dataLoadFailed"));
    } finally {
      setLoadingTabs(false);
    }
  };

  useEffect(() => {
    void loadOverview();
  }, []);

  useEffect(() => {
    void loadTabData();
  }, [targetKind]);

  const summary = overview ? (targetKind === "llm" ? overview.llm : overview.plugins) : null;
  const currentTabRecords = tabData ? tabData[TAB_LABELS(t)[activeTab].value as keyof UpgradesByLifecycleViewPayload] : null;

  const handleCancel = async (record: UpgradeRecordItem) => {
    const reason = window.prompt(t("upgrades.cancelReasonPrompt"));
    if (!reason || !reason.trim()) {
      return;
    }
    setActionLoadingRecordId(record.record_id);
    try {
      await cancelUpgradeRecord(record.record_id, reason.trim());
      await loadOverview();
      await loadTabData();
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : t("upgrades.cancelFailed"));
    } finally {
      setActionLoadingRecordId(null);
    }
  };

  const handleCleanupFailedCandidate = async (record: UpgradeRecordItem) => {
    const reason = window.prompt(t("upgrades.cleanupReasonPrompt"));
    if (!reason || !reason.trim()) {
      return;
    }
    setActionLoadingRecordId(record.record_id);
    try {
      await cleanupFailedCandidate(record.record_id, reason.trim());
      await loadOverview();
      await loadTabData();
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : t("upgrades.cleanupFailed"));
    } finally {
      setActionLoadingRecordId(null);
    }
  };

  const handleRowClick = (recordId: string) => {
    navigate(`/console/upgrades/${recordId}`);
  };

  return (
    <Stack spacing={3} data-testid="upgrade-management-root">
      {/* Header */}
      <Stack
        direction={{ xs: "column", md: "row" }}
        justifyContent="space-between"
        alignItems={{ xs: "flex-start", md: "center" }}
        spacing={2}
      >
        <Box>
          <Typography variant="h4" component="h1" gutterBottom>
            {t("upgrades.title")}
          </Typography>
          <Typography variant="body1" color="text.secondary">
            {t("upgrades.subtitle")}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" startIcon={<ArticleIcon />} onClick={() => navigate("/console/module-logs/upgrades")}>
            {t("moduleLogs.view")}
          </Button>
          <Button
            variant="contained"
            onClick={() => {
              void loadOverview();
              void loadTabData();
            }}
            disabled={loadingOverview || loadingTabs}
          >
            {loadingOverview || loadingTabs ? t("common.refreshing") : t("common.refresh")}
          </Button>
        </Stack>
      </Stack>

      {errorMessage && <Alert severity="error">{errorMessage}</Alert>}

      {/* Overview Cards */}
      <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
        <Card variant="outlined" sx={{ flex: 1 }}>
          <CardContent>
            <Typography variant="subtitle1" gutterBottom>
              {t("upgrades.llmUpgrade")}
            </Typography>
            {loadingOverview || overview === null ? (
              <CircularProgress size={20} />
            ) : (
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                <Chip label={`All: ${overview.llm.all}`} />
                <Chip label={`Waiting: ${overview.llm.waiting}`} color="warning" variant="outlined" />
                <Chip label={`Ongoing: ${overview.llm.ongoing}`} color="info" variant="outlined" />
                <Chip label={`Completed: ${overview.llm.completed}`} color="success" variant="outlined" />
                <Chip label={`Failed: ${overview.llm.failed}`} color="error" variant="outlined" />
                <Chip label={`Cancelled: ${overview.llm.cancelled}`} color="default" variant="outlined" />
              </Stack>
            )}
          </CardContent>
        </Card>
        <Card variant="outlined" sx={{ flex: 1 }}>
          <CardContent>
            <Typography variant="subtitle1" gutterBottom>
              {t("upgrades.pluginEvolution")}
            </Typography>
            {loadingOverview || overview === null ? (
              <CircularProgress size={20} />
            ) : (
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                <Chip label={`All: ${overview.plugins.all}`} />
                <Chip label={`Waiting: ${overview.plugins.waiting}`} color="warning" variant="outlined" />
                <Chip label={`Ongoing: ${overview.plugins.ongoing}`} color="info" variant="outlined" />
                <Chip label={`Completed: ${overview.plugins.completed}`} color="success" variant="outlined" />
                <Chip label={`Failed: ${overview.plugins.failed}`} color="error" variant="outlined" />
                <Chip label={`Cancelled: ${overview.plugins.cancelled}`} color="default" variant="outlined" />
              </Stack>
            )}
          </CardContent>
        </Card>
      </Stack>

      {/* Target Kind Filter */}
      <Stack direction="row" spacing={2} alignItems="center">
        <Stack direction="row" spacing={1}>
          <Button
            variant={targetKind === "llm" ? "contained" : "outlined"}
            onClick={() => setTargetKind("llm")}
          >
            LLM
          </Button>
          <Button
            variant={targetKind === "plugin" ? "contained" : "outlined"}
            onClick={() => setTargetKind("plugin")}
          >
            Plugin
          </Button>
        </Stack>

        {summary && (
          <Typography variant="body2" color="text.secondary">
            {t("upgrades.currentFilterStats", {
              all: summary.all,
              waiting: summary.waiting,
              ongoing: summary.ongoing,
              completed: summary.completed,
              failed: summary.failed,
              cancelled: summary.cancelled
            })}
          </Typography>
        )}
      </Stack>

      {/* Tabs */}
      <Paper variant="outlined">
        <Tabs
          value={activeTab}
          onChange={(_, newValue) => setActiveTab(newValue)}
          variant="scrollable"
          scrollButtons="auto"
        >
          {TAB_LABELS(t).map((tab, index) => {
            const count = tabData ? tabData[tab.value as keyof UpgradesByLifecycleViewPayload]?.count ?? 0 : 0;
            return (
              <Tab
                key={tab.value}
                label={`${tab.label} (${count})`}
                data-testid={`upgrade-tab-${tab.value}`}
              />
            );
          })}
        </Tabs>
      </Paper>

      {/* Tab Content */}
      {loadingTabs ? (
        <Paper variant="outlined">
          <Stack alignItems="center" justifyContent="center" sx={{ py: 8 }}>
            <CircularProgress />
          </Stack>
        </Paper>
      ) : currentTabRecords ? (
        <Paper variant="outlined">
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>{t("upgrades.colTitle")}</TableCell>
                  <TableCell>{t("upgrades.colTarget")}</TableCell>
                  <TableCell>{t("upgrades.colAction")}</TableCell>
                  <TableCell>{t("common.status")}</TableCell>
                  <TableCell>{t("upgrades.colProgress")}</TableCell>
                  <TableCell>{t("upgrades.colVersion")}</TableCell>
                  <TableCell>{t("upgrades.colAuditMemory")}</TableCell>
                  <TableCell align="right">{t("common.actions")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {currentTabRecords.items.map((item) => (
                  <TableRow
                    key={item.record_id}
                    hover
                    sx={{ cursor: "pointer" }}
                    onClick={() => handleRowClick(item.record_id)}
                  >
                    <TableCell>
                      <Typography variant="subtitle2">{item.title}</Typography>
                      <Typography variant="body2" color="text.secondary">
                        {item.reason}
                      </Typography>
                    </TableCell>
                    <TableCell>{item.target_id}</TableCell>
                    <TableCell>
                      <Chip size="small" variant="outlined" label={item.action} />
                    </TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={1}>
                        <Chip
                          size="small"
                          color={getLifecycleChipColor(item.lifecycle_view)}
                          label={item.lifecycle_view}
                        />
                        <Chip
                          size="small"
                          variant="outlined"
                          color={getLifecycleChipColor(item.current_status)}
                          label={item.current_status}
                        />
                      </Stack>
                    </TableCell>
                    <TableCell>{item.current_progress}%</TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {item.previous_version ? `${item.previous_version} -> ` : ""}
                        {item.candidate_version || item.current_version}
                      </Typography>
                    </TableCell>
                    <TableCell>{item.audit_status} / {item.memory_status}</TableCell>
                    <TableCell align="right">
                      <Stack direction="row" spacing={1} justifyContent="flex-end">
                        {item.can_cancel && (
                          <Button
                            size="small"
                            color="warning"
                            variant="outlined"
                            disabled={actionLoadingRecordId === item.record_id}
                            onClick={(event) => {
                              event.stopPropagation();
                              void handleCancel(item);
                            }}
                          >
                            {t("common.cancel")}
                          </Button>
                        )}
                        {item.can_cleanup_failed_candidate && (
                          <Button
                            size="small"
                            color="error"
                            variant="outlined"
                            disabled={actionLoadingRecordId === item.record_id}
                            onClick={(event) => {
                              event.stopPropagation();
                              void handleCleanupFailedCandidate(item);
                            }}
                          >
                            {t("upgrades.cleanupFailedCandidate")}
                          </Button>
                        )}
                      </Stack>
                    </TableCell>
                  </TableRow>
                ))}
                        {currentTabRecords.items.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={8}>
                      <Typography variant="body2" color="text.secondary" align="center" sx={{ py: 4 }}>
                        {t("upgrades.noRecordsInCategory")}
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      ) : null}
    </Stack>
  );
}
