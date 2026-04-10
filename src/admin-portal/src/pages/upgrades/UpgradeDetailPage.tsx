/**
 * Upgrade detail page showing comprehensive information about a specific upgrade record.
 * 
 * This page displays all details including basic info, success/failure information,
 * audit events, memory records, and provides action buttons for cancel/cleanup.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
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
  Snackbar,
  Stack,
  Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";

import {
  cancelUpgradeRecord,
  cleanupFailedCandidate,
  fetchUpgradeAuditEvents,
  fetchUpgradeMemoryRecords,
  fetchUpgradeRecord,
  type UpgradeAuditEventItem,
  type UpgradeMemoryRecordItem,
  type UpgradeRecordItem,
} from "./upgradesApi";

function formatDateTime(value?: string | null): string {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

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

export default function UpgradeDetailPage() {
  const { record_id } = useParams<{ record_id: string }>();
  const navigate = useNavigate();
  
  const [record, setRecord] = useState<UpgradeRecordItem | null>(null);
  const [auditEvents, setAuditEvents] = useState<UpgradeAuditEventItem[]>([]);
  const [memoryRecords, setMemoryRecords] = useState<UpgradeMemoryRecordItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!record_id) {
      setErrorMessage("缺少升级记录 ID");
      setLoading(false);
      return;
    }

    const loadData = async () => {
      setLoading(true);
      try {
        const [recordData, auditData, memoryData] = await Promise.all([
          fetchUpgradeRecord(record_id),
          fetchUpgradeAuditEvents(record_id),
          fetchUpgradeMemoryRecords(record_id),
        ]);
        setRecord(recordData);
        setAuditEvents(auditData);
        setMemoryRecords(memoryData);
        setErrorMessage(null);
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : "加载升级详情失败");
      } finally {
        setLoading(false);
      }
    };

    void loadData();
  }, [record_id]);

  const handleCancel = async () => {
    if (!record) return;
    
    const reason = window.prompt("请输入取消原因");
    if (!reason || !reason.trim()) {
      return;
    }

    setActionLoading(true);
    try {
      const updated = await cancelUpgradeRecord(record.record_id, reason.trim());
      setRecord(updated);
      setSuccessMessage("升级已取消");
      
      // 延迟跳转回列表页
      setTimeout(() => {
        navigate("/console/upgrades");
      }, 1500);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "取消升级失败");
    } finally {
      setActionLoading(false);
    }
  };

  const handleCleanupFailedCandidate = async () => {
    if (!record) return;
    
    const reason = window.prompt("请输入清理失败候选版本原因");
    if (!reason || !reason.trim()) {
      return;
    }

    setActionLoading(true);
    try {
      const updated = await cleanupFailedCandidate(record.record_id, reason.trim());
      setRecord(updated);
      setSuccessMessage("失败候选版本已清理");
      
      // 延迟跳转回列表页
      setTimeout(() => {
        navigate("/console/upgrades");
      }, 1500);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "清理失败候选版本失败");
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

  if (errorMessage && !record) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error">{errorMessage}</Alert>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate("/console/upgrades")}
          sx={{ mt: 2 }}
        >
          返回列表
        </Button>
      </Box>
    );
  }

  if (!record) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">未找到升级记录</Alert>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate("/console/upgrades")}
          sx={{ mt: 2 }}
        >
          返回列表
        </Button>
      </Box>
    );
  }

  return (
    <Stack spacing={3} sx={{ p: 3 }} data-testid="upgrade-detail-page">
      {/* Header */}
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate("/console/upgrades")}
          variant="outlined"
        >
          返回列表
        </Button>
        <Typography variant="h4" component="h1">
          升级详情
        </Typography>
        <Box sx={{ width: 100 }} /> {/* Spacer for alignment */}
      </Stack>

      {errorMessage && (
        <Alert severity="error" onClose={() => setErrorMessage(null)}>
          {errorMessage}
        </Alert>
      )}

      <Snackbar
        open={!!successMessage}
        autoHideDuration={3000}
        onClose={() => setSuccessMessage(null)}
        message={successMessage}
      />

      {/* Basic Information Card */}
      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <Box>
              <Typography variant="h5" gutterBottom>
                {record.title}
              </Typography>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                <Chip label={record.target_kind} />
                <Chip label={record.action} variant="outlined" />
                <Chip
                  label={record.current_status}
                  color={getLifecycleChipColor(record.current_status)}
                  variant="outlined"
                />
              </Stack>
            </Box>

            <Divider />

            <Typography variant="body2">
              <strong>Target:</strong> {record.target_id}
            </Typography>
            <Typography variant="body2">
              <strong>Reason:</strong> {record.reason}
            </Typography>
            <Typography variant="body2">
              <strong>Trace / Request:</strong> {record.trace_id} / {record.request_id}
            </Typography>
            {record.source_event_id && (
              <Typography variant="body2">
                <strong>Source Event:</strong> {record.source_event_id}
              </Typography>
            )}
            {record.parent_record_id && (
              <Typography variant="body2">
                <strong>Parent Record:</strong> {record.parent_record_id}
              </Typography>
            )}
            <Typography variant="body2">
              <strong>Function Summary:</strong> {record.function_summary}
            </Typography>
            <Typography variant="body2">
              <strong>Change Summary:</strong> {record.change_summary}
            </Typography>
            <Typography variant="body2">
              <strong>Version:</strong>{" "}
              {record.previous_version ? `${record.previous_version} -> ` : ""}
              {record.candidate_version || record.current_version}
            </Typography>
            <Typography variant="body2">
              <strong>Progress:</strong> {record.current_progress}%
            </Typography>
            <Typography variant="body2">
              <strong>Audit / Memory:</strong> {record.audit_status} / {record.memory_status}
            </Typography>
            <Typography variant="body2">
              <strong>Created:</strong> {formatDateTime(record.created_at)}
            </Typography>
            <Typography variant="body2">
              <strong>Updated:</strong> {formatDateTime(record.updated_at)}
            </Typography>
            {record.started_at && (
              <Typography variant="body2">
                <strong>Started:</strong> {formatDateTime(record.started_at)}
              </Typography>
            )}
            {record.finished_at && (
              <Typography variant="body2">
                <strong>Finished:</strong> {formatDateTime(record.finished_at)}
              </Typography>
            )}
            {record.source_path && (
              <Typography variant="body2">
                <strong>Source Path:</strong> {record.source_path}
              </Typography>
            )}
            {record.candidate_path && (
              <Typography variant="body2">
                <strong>Candidate Path:</strong> {record.candidate_path}
              </Typography>
            )}
            {record.evidence_refs.length > 0 && (
              <Typography variant="body2">
                <strong>Evidence Refs:</strong> {record.evidence_refs.join(", ")}
              </Typography>
            )}
          </Stack>
        </CardContent>
      </Card>

      {/* Success Information Card (only for completed status) */}
      {(record.current_status === "completed" || record.current_status === "cleaned_up") && (
        <Card variant="outlined" sx={{ borderColor: "success.main" }}>
          <CardContent>
            <Typography variant="h6" gutterBottom color="success.main">
              成功信息
            </Typography>
            <Stack spacing={1.5}>
              {record.success_stage && (
                <Typography variant="body2">
                  <strong>Success Stage:</strong> {record.success_stage}
                </Typography>
              )}
              {record.success_summary && (
                <Typography variant="body2">
                  <strong>Success Summary:</strong> {record.success_summary}
                </Typography>
              )}
              {record.reusable_insight && (
                <Typography variant="body2">
                  <strong>Reusable Insight:</strong> {record.reusable_insight}
                </Typography>
              )}
              {record.successful_command && (
                <Typography variant="body2">
                  <strong>Successful Command:</strong> {record.successful_command}
                </Typography>
              )}
              {record.success_artifact_refs.length > 0 && (
                <Typography variant="body2">
                  <strong>Success Artifacts:</strong> {record.success_artifact_refs.join(", ")}
                </Typography>
              )}
              {record.promotion_hint && (
                <Typography variant="body2">
                  <strong>Promotion Hint:</strong> {record.promotion_hint}
                </Typography>
              )}
              {record.success_tags.length > 0 && (
                <Typography variant="body2">
                  <strong>Success Tags:</strong> {record.success_tags.join(", ")}
                </Typography>
              )}
            </Stack>
          </CardContent>
        </Card>
      )}

      {/* Failure Information Card (only for failed/cancelled status) */}
      {(record.current_status === "failed" || record.current_status === "cancelled") && (
        <Card variant="outlined" sx={{ borderColor: "error.main" }}>
          <CardContent>
            <Typography variant="h6" gutterBottom color="error.main">
              失败信息
            </Typography>
            <Stack spacing={1.5}>
              {record.failure_reason && (
                <Alert severity="error" sx={{ mb: 1 }}>
                  <strong>Failure Reason:</strong> {record.failure_reason}
                </Alert>
              )}
              {record.failure_stage && (
                <Typography variant="body2">
                  <strong>Failure Stage:</strong> {record.failure_stage}
                </Typography>
              )}
              {record.failure_code && (
                <Typography variant="body2">
                  <strong>Failure Code:</strong> {record.failure_code}
                </Typography>
              )}
              {record.failure_summary && (
                <Typography variant="body2">
                  <strong>Failure Summary:</strong> {record.failure_summary}
                </Typography>
              )}
              {record.root_cause_hypothesis && (
                <Typography variant="body2">
                  <strong>Root Cause Hypothesis:</strong> {record.root_cause_hypothesis}
                </Typography>
              )}
              {record.failed_command && (
                <Typography variant="body2">
                  <strong>Failed Command:</strong> {record.failed_command}
                </Typography>
              )}
              {record.failed_artifact_refs.length > 0 && (
                <Typography variant="body2">
                  <strong>Failed Artifacts:</strong> {record.failed_artifact_refs.join(", ")}
                </Typography>
              )}
              {record.retryable !== undefined && record.retryable !== null && (
                <Typography variant="body2">
                  <strong>Retryable:</strong> {record.retryable ? "Yes" : "No"}
                </Typography>
              )}
              {record.prevention_hint && (
                <Typography variant="body2">
                  <strong>Prevention Hint:</strong> {record.prevention_hint}
                </Typography>
              )}
              {record.learning_tags.length > 0 && (
                <Typography variant="body2">
                  <strong>Learning Tags:</strong> {record.learning_tags.join(", ")}
                </Typography>
              )}
            </Stack>
          </CardContent>
        </Card>
      )}

      {/* Audit Events */}
      <Card variant="outlined">
        <CardContent>
          <Typography variant="h6" gutterBottom>
            审计事件
          </Typography>
          <Stack spacing={1.5}>
            {auditEvents.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                暂无审计事件。
              </Typography>
            ) : (
              auditEvents.map((event) => (
                <Paper key={event.event_id} variant="outlined" sx={{ p: 1.5 }}>
                  <Typography variant="body2">
                    <strong>{event.event_type}</strong> · {formatDateTime(event.created_at)}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {event.summary}
                  </Typography>
                </Paper>
              ))
            )}
          </Stack>
        </CardContent>
      </Card>

      {/* Memory Records */}
      <Card variant="outlined">
        <CardContent>
          <Typography variant="h6" gutterBottom>
            记忆记录
          </Typography>
          <Stack spacing={1.5}>
            {memoryRecords.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                暂无记忆记录。
              </Typography>
            ) : (
              memoryRecords.map((item) => (
                <Paper key={item.memory_id} variant="outlined" sx={{ p: 1.5 }}>
                  <Typography variant="body2">
                    <strong>{item.event_type}</strong> · {formatDateTime(item.created_at)}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {item.summary}
                  </Typography>
                </Paper>
              ))
            )}
          </Stack>
        </CardContent>
      </Card>

      {/* Action Buttons */}
      <Stack direction="row" spacing={2} justifyContent="flex-end">
        {record.can_cancel && (
          <Button
            color="warning"
            variant="contained"
            disabled={actionLoading}
            onClick={handleCancel}
          >
            {actionLoading ? "处理中..." : "取消升级"}
          </Button>
        )}
        {record.can_cleanup_failed_candidate && (
          <Button
            color="error"
            variant="contained"
            disabled={actionLoading}
            onClick={handleCleanupFailedCandidate}
          >
            {actionLoading ? "处理中..." : "清理失败候选"}
          </Button>
        )}
      </Stack>
    </Stack>
  );
}
