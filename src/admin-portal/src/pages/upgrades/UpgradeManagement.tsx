/**
 * Upgrade management console for LLM optimization and plugin evolution jobs.
 *
 * This page lets operators inspect waiting, ongoing, completed, and failed
 * upgrade or plugin creation records without digging through raw audit events.
 */
import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Drawer,
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
  Typography,
} from "@mui/material";

import {
  cancelUpgradeRecord,
  cleanupFailedCandidate,
  fetchUpgradeAuditEvents,
  fetchUpgradeCollection,
  fetchUpgradeMemoryRecords,
  fetchUpgradeOverview,
  fetchUpgradeRecord,
  type UpgradeAuditEventItem,
  type UpgradeLifecycle,
  type UpgradeMemoryRecordItem,
  type UpgradeOverviewPayload,
  type UpgradeRecordCollection,
  type UpgradeRecordItem,
  type UpgradeTargetKind,
} from "./upgradesApi";

const LIFECYCLE_OPTIONS: UpgradeLifecycle[] = [
  "all",
  "waiting",
  "ongoing",
  "completed",
  "failed",
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
  const [targetKind, setTargetKind] = useState<UpgradeTargetKind>("llm");
  const [lifecycle, setLifecycle] = useState<UpgradeLifecycle>("all");
  const [pluginAction, setPluginAction] = useState<"all" | "upgrade" | "create">("all");
  const [overview, setOverview] = useState<UpgradeOverviewPayload | null>(null);
  const [collection, setCollection] = useState<UpgradeRecordCollection | null>(null);
  const [selectedRecord, setSelectedRecord] = useState<UpgradeRecordItem | null>(null);
  const [selectedAuditEvents, setSelectedAuditEvents] = useState<UpgradeAuditEventItem[]>([]);
  const [selectedMemoryRecords, setSelectedMemoryRecords] = useState<UpgradeMemoryRecordItem[]>([]);
  const [loadingOverview, setLoadingOverview] = useState(true);
  const [loadingList, setLoadingList] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionLoadingRecordId, setActionLoadingRecordId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const loadOverview = async () => {
    setLoadingOverview(true);
    try {
      const payload = await fetchUpgradeOverview();
      setOverview(payload);
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "升级总览加载失败");
    } finally {
      setLoadingOverview(false);
    }
  };

  const loadCollection = async () => {
    setLoadingList(true);
    try {
      const payload = await fetchUpgradeCollection(targetKind, lifecycle, pluginAction);
      setCollection(payload);
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "升级列表加载失败");
    } finally {
      setLoadingList(false);
    }
  };

  useEffect(() => {
    void loadOverview();
  }, []);

  useEffect(() => {
    void loadCollection();
  }, [targetKind, lifecycle, pluginAction]);

  const summary = useMemo(() => {
    if (!overview) {
      return null;
    }
    return targetKind === "llm" ? overview.llm : overview.plugins;
  }, [overview, targetKind]);

  const handleOpenRecord = async (recordId: string) => {
    setDetailLoading(true);
    try {
      const [record, auditEvents, memoryRecords] = await Promise.all([
        fetchUpgradeRecord(recordId),
        fetchUpgradeAuditEvents(recordId),
        fetchUpgradeMemoryRecords(recordId),
      ]);
      setSelectedRecord(record);
      setSelectedAuditEvents(auditEvents);
      setSelectedMemoryRecords(memoryRecords);
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "升级详情加载失败");
    } finally {
      setDetailLoading(false);
    }
  };

  const handleCancel = async (record: UpgradeRecordItem) => {
    const reason = window.prompt("请输入取消原因");
    if (!reason || !reason.trim()) {
      return;
    }
    setActionLoadingRecordId(record.record_id);
    try {
      const updated = await cancelUpgradeRecord(record.record_id, reason.trim());
      setSelectedRecord((current) => (current?.record_id === updated.record_id ? updated : current));
      await loadOverview();
      await loadCollection();
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "取消升级失败");
    } finally {
      setActionLoadingRecordId(null);
    }
  };

  const handleCleanupFailedCandidate = async (record: UpgradeRecordItem) => {
    const reason = window.prompt("请输入清理失败候选版本原因");
    if (!reason || !reason.trim()) {
      return;
    }
    setActionLoadingRecordId(record.record_id);
    try {
      const updated = await cleanupFailedCandidate(record.record_id, reason.trim());
      setSelectedRecord((current) => (current?.record_id === updated.record_id ? updated : current));
      await loadOverview();
      await loadCollection();
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "清理失败候选版本失败");
    } finally {
      setActionLoadingRecordId(null);
    }
  };

  return (
    <Stack spacing={3} data-testid="upgrade-management-root">
      <Stack
        direction={{ xs: "column", md: "row" }}
        justifyContent="space-between"
        alignItems={{ xs: "flex-start", md: "center" }}
        spacing={2}
      >
        <Box>
          <Typography variant="h4" component="h1" gutterBottom>
            升级管理
          </Typography>
          <Typography variant="body1" color="text.secondary">
            查看 LLM 升级、插件升级、插件创建的 waiting / ongoing / completed / failed 状态。
          </Typography>
        </Box>
        <Button
          variant="contained"
          onClick={() => {
            void loadOverview();
            void loadCollection();
          }}
          disabled={loadingOverview || loadingList}
        >
          {loadingOverview || loadingList ? "刷新中…" : "刷新"}
        </Button>
      </Stack>

      {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}

      <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
        <Card variant="outlined" sx={{ flex: 1 }}>
          <CardContent>
            <Typography variant="subtitle1" gutterBottom>
              LLM Upgrade
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
              </Stack>
            )}
          </CardContent>
        </Card>
        <Card variant="outlined" sx={{ flex: 1 }}>
          <CardContent>
            <Typography variant="subtitle1" gutterBottom>
              Plugin Evolution
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
              </Stack>
            )}
          </CardContent>
        </Card>
      </Stack>

      <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems={{ md: "center" }}>
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

        <Select
          size="small"
          value={lifecycle}
          onChange={(event) => setLifecycle(event.target.value as UpgradeLifecycle)}
          data-testid="upgrade-lifecycle-filter"
        >
          {LIFECYCLE_OPTIONS.map((option) => (
            <MenuItem key={option} value={option}>
              {option}
            </MenuItem>
          ))}
        </Select>

        {targetKind === "plugin" ? (
          <Select
            size="small"
            value={pluginAction}
            onChange={(event) => setPluginAction(event.target.value as "all" | "upgrade" | "create")}
            data-testid="upgrade-plugin-action-filter"
          >
            <MenuItem value="all">all actions</MenuItem>
            <MenuItem value="upgrade">upgrade only</MenuItem>
            <MenuItem value="create">create only</MenuItem>
          </Select>
        ) : null}

        {summary ? (
          <Typography variant="body2" color="text.secondary">
            当前筛选统计: all {summary.all} / waiting {summary.waiting} / ongoing {summary.ongoing} / completed {summary.completed} / failed {summary.failed}
          </Typography>
        ) : null}
      </Stack>

      {loadingList || collection === null ? (
        <Paper variant="outlined">
          <Stack alignItems="center" justifyContent="center" sx={{ py: 8 }}>
            <CircularProgress />
          </Stack>
        </Paper>
      ) : (
        <Paper variant="outlined">
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Title</TableCell>
                  <TableCell>Target</TableCell>
                  <TableCell>Action</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Progress</TableCell>
                  <TableCell>Version</TableCell>
                  <TableCell>Audit / Memory</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {collection.items.map((item) => (
                  <TableRow
                    key={item.record_id}
                    hover
                    sx={{ cursor: "pointer" }}
                    onClick={() => void handleOpenRecord(item.record_id)}
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
                        <Button size="small" variant="outlined" onClick={(event) => {
                          event.stopPropagation();
                          void handleOpenRecord(item.record_id);
                        }}>
                          查看
                        </Button>
                        {item.can_cancel ? (
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
                            取消
                          </Button>
                        ) : null}
                        {item.can_cleanup_failed_candidate ? (
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
                            清理失败候选
                          </Button>
                        ) : null}
                      </Stack>
                    </TableCell>
                  </TableRow>
                ))}
                {collection.items.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8}>
                      <Typography variant="body2" color="text.secondary">
                        当前筛选下没有记录。
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      )}

      <Drawer anchor="right" open={selectedRecord !== null} onClose={() => {
        setSelectedRecord(null);
        setSelectedAuditEvents([]);
        setSelectedMemoryRecords([]);
      }}>
        <Box sx={{ width: { xs: 320, sm: 460 }, p: 3 }} data-testid="upgrade-detail-drawer">
          {detailLoading ? (
            <CircularProgress />
          ) : selectedRecord ? (
            <Stack spacing={2}>
              <Box>
                <Typography variant="h5" gutterBottom>
                  {selectedRecord.title}
                </Typography>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                  <Chip label={selectedRecord.target_kind} />
                  <Chip label={selectedRecord.action} variant="outlined" />
                  <Chip
                    label={selectedRecord.current_status}
                    color={getLifecycleChipColor(selectedRecord.current_status)}
                    variant="outlined"
                  />
                </Stack>
              </Box>

              <Divider />

              <Typography variant="body2">
                <strong>Target:</strong> {selectedRecord.target_id}
              </Typography>
              <Typography variant="body2">
                <strong>Reason:</strong> {selectedRecord.reason}
              </Typography>
              <Typography variant="body2">
                <strong>Trace / Request:</strong> {selectedRecord.trace_id} / {selectedRecord.request_id}
              </Typography>
              {selectedRecord.source_event_id ? (
                <Typography variant="body2">
                  <strong>Source Event:</strong> {selectedRecord.source_event_id}
                </Typography>
              ) : null}
              {selectedRecord.parent_record_id ? (
                <Typography variant="body2">
                  <strong>Parent Record:</strong> {selectedRecord.parent_record_id}
                </Typography>
              ) : null}
              <Typography variant="body2">
                <strong>Function Summary:</strong> {selectedRecord.function_summary}
              </Typography>
              <Typography variant="body2">
                <strong>Change Summary:</strong> {selectedRecord.change_summary}
              </Typography>
              <Typography variant="body2">
                <strong>Version:</strong> {selectedRecord.previous_version ? `${selectedRecord.previous_version} -> ` : ""}
                {selectedRecord.candidate_version || selectedRecord.current_version}
              </Typography>
              <Typography variant="body2">
                <strong>Progress:</strong> {selectedRecord.current_progress}%
              </Typography>
              <Typography variant="body2">
                <strong>Audit / Memory:</strong> {selectedRecord.audit_status} / {selectedRecord.memory_status}
              </Typography>
              <Typography variant="body2">
                <strong>Created:</strong> {formatDateTime(selectedRecord.created_at)}
              </Typography>
              <Typography variant="body2">
                <strong>Updated:</strong> {formatDateTime(selectedRecord.updated_at)}
              </Typography>
              {selectedRecord.source_path ? (
                <Typography variant="body2">
                  <strong>Source Path:</strong> {selectedRecord.source_path}
                </Typography>
              ) : null}
              {selectedRecord.candidate_path ? (
                <Typography variant="body2">
                  <strong>Candidate Path:</strong> {selectedRecord.candidate_path}
                </Typography>
              ) : null}
              {selectedRecord.evidence_refs.length > 0 ? (
                <Typography variant="body2">
                  <strong>Evidence Refs:</strong> {selectedRecord.evidence_refs.join(", ")}
                </Typography>
              ) : null}
              {selectedRecord.success_summary ? (
                <Typography variant="body2">
                  <strong>Success Summary:</strong> {selectedRecord.success_summary}
                </Typography>
              ) : null}
              {selectedRecord.success_stage ? (
                <Typography variant="body2">
                  <strong>Success Stage:</strong> {selectedRecord.success_stage}
                </Typography>
              ) : null}
              {selectedRecord.reusable_insight ? (
                <Typography variant="body2">
                  <strong>Reusable Insight:</strong> {selectedRecord.reusable_insight}
                </Typography>
              ) : null}
              {selectedRecord.successful_command ? (
                <Typography variant="body2">
                  <strong>Successful Command:</strong> {selectedRecord.successful_command}
                </Typography>
              ) : null}
              {(selectedRecord.success_artifact_refs ?? []).length > 0 ? (
                <Typography variant="body2">
                  <strong>Success Artifacts:</strong> {(selectedRecord.success_artifact_refs ?? []).join(", ")}
                </Typography>
              ) : null}
              {selectedRecord.promotion_hint ? (
                <Typography variant="body2">
                  <strong>Promotion Hint:</strong> {selectedRecord.promotion_hint}
                </Typography>
              ) : null}
              {(selectedRecord.success_tags ?? []).length > 0 ? (
                <Typography variant="body2">
                  <strong>Success Tags:</strong> {(selectedRecord.success_tags ?? []).join(", ")}
                </Typography>
              ) : null}
              {selectedRecord.failure_reason ? (
                <Alert severity="error">
                  <strong>Failure:</strong> {selectedRecord.failure_reason}
                </Alert>
              ) : null}
              {selectedRecord.failure_summary ? (
                <Typography variant="body2">
                  <strong>Failure Summary:</strong> {selectedRecord.failure_summary}
                </Typography>
              ) : null}
              {selectedRecord.failure_stage ? (
                <Typography variant="body2">
                  <strong>Failure Stage:</strong> {selectedRecord.failure_stage}
                </Typography>
              ) : null}
              {selectedRecord.failure_code ? (
                <Typography variant="body2">
                  <strong>Failure Code:</strong> {selectedRecord.failure_code}
                </Typography>
              ) : null}
              {selectedRecord.root_cause_hypothesis ? (
                <Typography variant="body2">
                  <strong>Root Cause Hypothesis:</strong> {selectedRecord.root_cause_hypothesis}
                </Typography>
              ) : null}
              {selectedRecord.failed_command ? (
                <Typography variant="body2">
                  <strong>Failed Command:</strong> {selectedRecord.failed_command}
                </Typography>
              ) : null}
              {(selectedRecord.failed_artifact_refs ?? []).length > 0 ? (
                <Typography variant="body2">
                  <strong>Failed Artifacts:</strong> {(selectedRecord.failed_artifact_refs ?? []).join(", ")}
                </Typography>
              ) : null}
              {selectedRecord.retryable !== undefined && selectedRecord.retryable !== null ? (
                <Typography variant="body2">
                  <strong>Retryable:</strong> {selectedRecord.retryable ? "yes" : "no"}
                </Typography>
              ) : null}
              {selectedRecord.prevention_hint ? (
                <Typography variant="body2">
                  <strong>Prevention Hint:</strong> {selectedRecord.prevention_hint}
                </Typography>
              ) : null}
              {(selectedRecord.learning_tags ?? []).length > 0 ? (
                <Typography variant="body2">
                  <strong>Learning Tags:</strong> {(selectedRecord.learning_tags ?? []).join(", ")}
                </Typography>
              ) : null}

              <Divider />

              <Box>
                <Typography variant="subtitle2" gutterBottom>
                  审计事件
                </Typography>
                <Stack spacing={1}>
                  {selectedAuditEvents.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">
                      暂无审计事件。
                    </Typography>
                  ) : selectedAuditEvents.map((event) => (
                    <Paper key={event.event_id} variant="outlined" sx={{ p: 1.5 }}>
                      <Typography variant="body2">
                        <strong>{event.event_type}</strong> · {formatDateTime(event.created_at)}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {event.summary}
                      </Typography>
                    </Paper>
                  ))}
                </Stack>
              </Box>

              <Box>
                <Typography variant="subtitle2" gutterBottom>
                  记忆记录
                </Typography>
                <Stack spacing={1}>
                  {selectedMemoryRecords.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">
                      暂无记忆记录。
                    </Typography>
                  ) : selectedMemoryRecords.map((item) => (
                    <Paper key={item.memory_id} variant="outlined" sx={{ p: 1.5 }}>
                      <Typography variant="body2">
                        <strong>{item.event_type}</strong> · {formatDateTime(item.created_at)}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {item.summary}
                      </Typography>
                    </Paper>
                  ))}
                </Stack>
              </Box>
              <Stack direction="row" spacing={1}>
                {selectedRecord.can_cancel ? (
                  <Button
                    color="warning"
                    variant="outlined"
                    disabled={actionLoadingRecordId === selectedRecord.record_id}
                    onClick={() => void handleCancel(selectedRecord)}
                  >
                    取消升级
                  </Button>
                ) : null}
                {selectedRecord.can_cleanup_failed_candidate ? (
                  <Button
                    color="error"
                    variant="outlined"
                    disabled={actionLoadingRecordId === selectedRecord.record_id}
                    onClick={() => void handleCleanupFailedCandidate(selectedRecord)}
                  >
                    清理失败候选
                  </Button>
                ) : null}
              </Stack>
            </Stack>
          ) : null}
        </Box>
      </Drawer>
    </Stack>
  );
}
