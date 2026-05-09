import { useTranslation } from 'react-i18next';
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Typography,
  Button,
  Stack,
  Card,
  CardContent,
  Chip,
  Divider,
  Alert,
  CircularProgress,
  IconButton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
} from '@mui/material';
import {
  ArrowBack as BackIcon,
  Article as LogsIcon,
  ContentCopy as CopyIcon,
  Delete as DeleteIcon,
  ExpandMore as ExpandMoreIcon,
  Replay as RetryIcon,
} from '@mui/icons-material';
import { ZentexTask } from './types';
import StatusChip from './TaskStatusChip';
import {
  canRetryTask,
  formatBlockedReason,
  formatExecutionParty,
  formatTaskVerificationMethod,
  formatTaskDateTime,
  taskEndTime,
  taskStartTime,
} from './taskDisplay';

interface TaskDetailData {
  task: ZentexTask;
  subtasks: ZentexTask[];
  subtask_count: number;
  dependencies: Array<{ task_id: string; title: string; status: string }>;
  dependents: Array<{ task_id: string; title: string; status: string }>;
  interventions: any[];
  statistics: {
    total_subtasks: number;
    completed_subtasks: number;
    in_progress_subtasks: number;
    pending_subtasks: number;
    failed_subtasks: number;
  };
}

const isRecord = (value: unknown): value is Record<string, any> => {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
};

const formatScalar = (value: unknown): string => {
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false';
  }
  if (typeof value === 'string' || typeof value === 'number') {
    return String(value);
  }
  if (Array.isArray(value)) {
    return `${value.length}`;
  }
  if (isRecord(value)) {
    return `${Object.keys(value).length}`;
  }
  return String(value);
};

const metadataPathValue = (metadata: Record<string, any>, path: string): unknown => {
  return path.split('.').reduce<unknown>((current, key) => {
    if (!isRecord(current)) {
      return undefined;
    }
    return current[key];
  }, metadata);
};

const compactObjectEntries = (value: unknown): Array<[string, unknown]> => {
  if (!isRecord(value)) {
    return [];
  }
  return Object.entries(value).filter(([, item]) => !isRecord(item) && !Array.isArray(item));
};

const firstReadableValue = (...values: unknown[]): string => {
  for (const value of values) {
    if (typeof value === 'string' && value.trim().length > 0) {
      return value.trim();
    }
    if (typeof value === 'number' || typeof value === 'boolean') {
      return String(value);
    }
    if (Array.isArray(value)) {
      const items = value.map((item) => formatScalar(item)).filter((item) => item !== '-');
      if (items.length > 0) {
        return items.join('；');
      }
    }
  }
  return '-';
};

const formatSubtaskObjective = (subtask: ZentexTask): string => {
  const metadata = subtask.metadata || {};
  const contract = subtask.contract || {};
  const expectedOutcome = isRecord(contract.expected_outcome) ? contract.expected_outcome : {};
  return firstReadableValue(
    metadata.objective,
    metadata.intent_objective,
    expectedOutcome.objective,
    subtask.remarks,
  );
};

const formatSubtaskExceptionReason = (subtask: ZentexTask): string => {
  const metadata = subtask.metadata || {};
  const dispatchFailure = isRecord(metadata.dispatch_failure) ? metadata.dispatch_failure : {};
  const timeoutRecovery = isRecord(metadata.timeout_recovery) ? metadata.timeout_recovery : {};
  return firstReadableValue(
    subtask.last_error,
    dispatchFailure.message,
    dispatchFailure.reason,
    timeoutRecovery.message,
    timeoutRecovery.recovery_error,
    metadata.blocked_reason,
    metadata.block_reason,
    metadata.error_reason,
    metadata.failure_reason,
  );
};

const summarizeNestedValue = (value: unknown, t: ReturnType<typeof useTranslation>['t']): string => {
  if (Array.isArray(value)) {
    return t('tasks.metadataArrayCount', { count: value.length });
  }
  if (isRecord(value)) {
    const entries = compactObjectEntries(value).slice(0, 3);
    if (entries.length > 0) {
      return entries.map(([key, item]) => `${key}: ${formatScalar(item)}`).join(' · ');
    }
    return t('tasks.metadataFieldCount', { count: Object.keys(value).length });
  }
  return formatScalar(value);
};

const TaskDetailPage: React.FC = () => {
  const { t } = useTranslation();
  const { task_id } = useParams<{ task_id: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [taskData, setTaskData] = useState<TaskDetailData | null>(null);

  useEffect(() => {
    if (!task_id) {
      setError(t('tasks.idNotFound'));
      setLoading(false);
      return;
    }

    fetchTaskDetail(task_id);
  }, [task_id]);

  const fetchTaskDetail = async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/web/tasks/${id}/detail`);
      if (!res.ok) {
        throw new Error(`${t('tasks.fetchDetailFailed')}（HTTP ${res.status}）`);
      }
      const data: TaskDetailData = await res.json();
      setTaskData(data);
    } catch (err) {
      console.error('Failed to fetch task detail', err);
      setError(err instanceof Error ? err.message : t('tasks.fetchDetailFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleCopyId = () => {
    if (taskData) {
      navigator.clipboard.writeText(taskData.task.task_id);
    }
  };

  const handleBack = () => {
    navigate('/console/tasks');
  };

  const handleViewSubtask = (subtaskId: string) => {
    navigate(`/console/tasks/${subtaskId}`);
  };

  const handleViewTaskLogs = () => {
    if (taskData) {
      navigate(`/console/tasks/${taskData.task.task_id}/logs`);
    }
  };

  const handleRetryTask = async () => {
    if (!taskData) {
      return;
    }
    const task = taskData.task;
    try {
      const response = await fetch(`/api/web/tasks/${task.task_id}/intervene`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'retry',
          idempotency_key: `retry-${task.task_id}-${Date.now()}`,
          remarks: t('tasks.retryRemarks'),
          operator_id: 'web-console',
        }),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      await fetchTaskDetail(task.task_id);
    } catch (err) {
      console.error('Failed to retry task', err);
      window.alert(t('tasks.retryFailed'));
    }
  };

  const handleArchiveTask = async () => {
    if (!taskData) {
      return;
    }
    const task = taskData.task;
    if (!window.confirm(t('tasks.archiveConfirm'))) {
      return;
    }
    try {
      const response = await fetch(`/api/web/tasks/${task.task_id}/intervene`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'archive',
          idempotency_key: `archive-${task.task_id}-${Date.now()}`,
          remarks: t('tasks.archiveRemarks'),
          operator_id: 'web-console',
        }),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      navigate('/console/tasks');
    } catch (err) {
      console.error('Failed to archive task', err);
      window.alert(t('tasks.archiveFailed'));
    }
  };

  const formatToken = (namespace: string, value?: string | null) => {
    if (!value) {
      return t('common.unknown', { defaultValue: '未知' });
    }
    return t(`${namespace}.${value}`, { defaultValue: String(value).replace(/_/g, ' ') });
  };

  const formatTaskDescription = (task: ZentexTask) => {
    return task.remarks || task.metadata?.description || task.metadata?.summary || task.metadata?.objective || t('tasks.noDescription');
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error || !taskData) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error">{error || t('tasks.notFound')}</Alert>
        <Button startIcon={<BackIcon />} onClick={handleBack} sx={{ mt: 2 }}>
          {t('tasks.backToList')}
        </Button>
      </Box>
    );
  }

  const { task, subtasks, statistics, dependencies, dependents, interventions } = taskData;
  const executorLabel = formatExecutionParty(task, t);
  const blockedReason = formatBlockedReason(task, t);
  const metadata = task.metadata || {};
  const hasMetadata = Object.keys(metadata).length > 0;
  const metadataHighlights = [
    { label: t('tasks.sourceModule'), value: (task.metadata?.source_module || task.metadata?.source)
      ? t(`tasks.sourceModules.${task.metadata.source_module || task.metadata.source}`, {
          defaultValue: String(task.metadata.source_module || task.metadata.source).replace(/[_-]/g, ' '),
        })
      : t('tasks.none') },
    { label: t('tasks.workflowStatus'), value: task.metadata?.workflow_status
      ? t(`tasks.workflowStatuses.${task.metadata.workflow_status}`, {
          defaultValue: String(task.metadata.workflow_status).replace(/_/g, ' '),
        })
      : t('tasks.none') },
    { label: t('tasks.workflowProgress'), value: formatScalar(task.metadata?.workflow_progress) },
    { label: t('tasks.metadataFields.queueName'), value: formatScalar(task.metadata?.queue_name) },
    { label: t('tasks.metadataFields.executorType'), value: formatScalar(task.metadata?.executor_type) },
    { label: t('tasks.metadataFields.targetId'), value: formatScalar(task.metadata?.target_id) },
    { label: t('tasks.metadataFields.requiredCapability'), value: formatScalar(task.metadata?.required_capability) },
    { label: t('tasks.metadataFields.toolId'), value: formatScalar(task.metadata?.tool_id) },
  ].filter((item) => item.value !== '-' && item.value !== t('tasks.none'));
  const metadataTextItems = [
    { label: t('tasks.metadataFields.objective'), value: task.metadata?.objective },
    { label: t('tasks.metadataFields.summary'), value: task.metadata?.summary },
    { label: t('tasks.metadataFields.creationReason'), value: task.metadata?.creation_reason },
    { label: t('tasks.metadataFields.blockedReason'), value: task.metadata?.blocked_reason || task.metadata?.block_reason },
    { label: t('tasks.metadataFields.recoveryCondition'), value: task.metadata?.recovery_condition || task.metadata?.resume_condition },
    { label: t('tasks.metadataFields.lastError'), value: task.metadata?.last_error || task.last_error },
  ].filter((item) => typeof item.value === 'string' && item.value.trim().length > 0);
  const metadataSections = [
    { label: t('tasks.metadataFields.dispatchFailure'), value: metadataPathValue(metadata, 'dispatch_failure') },
    { label: t('tasks.metadataFields.timeoutRecovery'), value: metadataPathValue(metadata, 'timeout_recovery') },
    { label: t('tasks.metadataFields.negotiation'), value: metadataPathValue(metadata, 'negotiation') },
    { label: t('tasks.metadataFields.verification'), value: metadataPathValue(metadata, 'verification') || metadataPathValue(metadata, 'verification_result') },
    { label: t('tasks.metadataFields.rawPayload'), value: metadataPathValue(metadata, 'raw_payload') },
  ].filter((item) => item.value !== undefined && item.value !== null);
  const executorSourceLabel = task.execution_assignment?.source
    ? t(`tasks.assignmentSources.${task.execution_assignment.source}`, {
        defaultValue: String(task.execution_assignment.source).replace(/_/g, ' '),
      })
    : '';

  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={3}>
        {/* Header */}
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Stack direction="row" spacing={2} alignItems="center">
            <IconButton onClick={handleBack}>
              <BackIcon />
            </IconButton>
            <Typography variant="h4" component="h1">
              {t('tasks.detailTitle')}
            </Typography>
          </Stack>
          <Stack direction="row" spacing={1}>
            <Button
              variant="outlined"
              startIcon={<LogsIcon />}
              onClick={handleViewTaskLogs}
            >
              {t('tasks.logs.viewTaskLogs')}
            </Button>
            {canRetryTask(task) ? (
              <Button
                variant="contained"
                color="warning"
                startIcon={<RetryIcon />}
                onClick={handleRetryTask}
              >
                {t('tasks.retry')}
              </Button>
            ) : null}
            <Button
              variant="outlined"
              color="error"
              startIcon={<DeleteIcon />}
              onClick={handleArchiveTask}
            >
              {t('tasks.archive')}
            </Button>
            <Button
              variant="outlined"
              startIcon={<BackIcon />}
              onClick={handleBack}
            >
              {t('tasks.backToList')}
            </Button>
          </Stack>
        </Stack>

        {/* Basic Info Card */}
        <Card>
          <CardContent>
            <Stack spacing={2}>
              <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                <Box>
                  <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                    <Typography variant="h5" component="span">
                      {task.title}
                    </Typography>
                    <Tooltip title={t('tasks.copyTaskId')}>
                      <IconButton size="small" onClick={handleCopyId}>
                        <CopyIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Stack>
                  <Typography variant="body2" color="text.secondary">
                    ID: {task.task_id}
                  </Typography>
                </Box>
                <StatusChip status={task.status} />
              </Stack>

              <Divider />

              <Box>
                <Typography variant="subtitle2" color="text.secondary">{t('tasks.description')}</Typography>
                <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap' }}>
                  {formatTaskDescription(task)}
                </Typography>
              </Box>

              <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
                <Box>
                  <Typography variant="subtitle2" color="text.secondary">{t('tasks.type')}</Typography>
                  <Typography variant="body1">{formatToken('tasks.types', task.task_type)}</Typography>
                </Box>
                <Box>
                  <Typography variant="subtitle2" color="text.secondary">{t('tasks.taskScope')}</Typography>
                  <Typography variant="body1">{formatToken('tasks.scopes', task.task_scope || 'internal')}</Typography>
                </Box>
                <Box>
                  <Typography variant="subtitle2" color="text.secondary">{t('tasks.priority')}</Typography>
                  <Typography variant="body1">{formatToken('tasks.priorities', task.priority || 'medium')}</Typography>
                </Box>
                <Box>
                  <Typography variant="subtitle2" color="text.secondary">{t('tasks.originator')}</Typography>
                  <Typography variant="body1">{task.originator_id}</Typography>
                </Box>
                <Box>
                  <Typography variant="subtitle2" color="text.secondary">{t('tasks.executor')}</Typography>
                  <Typography variant="body1">{executorLabel}</Typography>
                  {executorSourceLabel ? (
                    <Typography variant="caption" color="text.secondary">
                      {executorSourceLabel}
                    </Typography>
                  ) : null}
                </Box>
                {task.status === 'blocked' ? (
                  <Box>
                    <Typography variant="subtitle2" color="text.secondary">{t('tasks.blockedReason')}</Typography>
                    <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {blockedReason}
                    </Typography>
                  </Box>
                ) : null}
                <Box>
                  <Typography variant="subtitle2" color="text.secondary">{t('tasks.createdAt')}</Typography>
                  <Typography variant="body1">
                    {task.created_at ? new Date(task.created_at).toLocaleString() : '-'}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="subtitle2" color="text.secondary">{t('tasks.taskStartedAt')}</Typography>
                  <Typography variant="body1">
                    {formatTaskDateTime(taskStartTime(task))}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="subtitle2" color="text.secondary">{t('tasks.taskEndedAt')}</Typography>
                  <Typography variant="body1">
                    {formatTaskDateTime(taskEndTime(task))}
                  </Typography>
                </Box>
              </Box>
            </Stack>
          </CardContent>
        </Card>

        {/* Subtasks Flow Table */}
        <Card id="subtasks">
          <CardContent>
            <Typography variant="h6" gutterBottom>
              {t('tasks.subtaskFlow')} ({statistics.total_subtasks})
            </Typography>

            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, 1fr)', md: 'repeat(4, 1fr)' }, gap: 2, mb: 2 }}>
              <Chip label={`${t('tasks.completed')}: ${statistics.completed_subtasks}`} color="success" size="small" />
              <Chip label={`${t('tasks.inProgress')}: ${statistics.in_progress_subtasks}`} color="primary" size="small" />
              <Chip label={`${t('tasks.pending')}: ${statistics.pending_subtasks}`} color="warning" size="small" />
              <Chip label={`${t('tasks.failed')}: ${statistics.failed_subtasks}`} color="error" size="small" />
            </Box>

            {subtasks.length === 0 ? (
              <Alert severity="info">{t('tasks.noSubtasks')}</Alert>
            ) : (
              <TableContainer sx={{ overflowX: 'auto' }}>
                <Table size="small" aria-label={t('tasks.subtaskFlow')}>
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ width: 72 }}>{t('tasks.flowStep')}</TableCell>
                      <TableCell sx={{ minWidth: 220 }}>{t('tasks.subtaskName')}</TableCell>
                      <TableCell sx={{ minWidth: 240 }}>{t('tasks.metadataFields.objective')}</TableCell>
                      <TableCell sx={{ minWidth: 240 }}>{t('tasks.verificationMethod')}</TableCell>
                      <TableCell sx={{ minWidth: 160 }}>{t('tasks.executor')}</TableCell>
                      <TableCell sx={{ minWidth: 170 }}>{t('tasks.taskStartedAt')}</TableCell>
                      <TableCell sx={{ minWidth: 170 }}>{t('tasks.taskEndedAt')}</TableCell>
                      <TableCell sx={{ minWidth: 130 }}>{t('tasks.status')}</TableCell>
                      <TableCell sx={{ minWidth: 220 }}>{t('tasks.exceptionReason')}</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {subtasks.map((subtask, index) => (
                      <TableRow
                        key={subtask.task_id}
                        hover
                        onClick={() => handleViewSubtask(subtask.task_id)}
                        sx={{ cursor: 'pointer', verticalAlign: 'top' }}
                      >
                        <TableCell>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <Box
                              sx={{
                                width: 26,
                                height: 26,
                                borderRadius: '50%',
                                bgcolor: 'primary.main',
                                color: 'primary.contrastText',
                                display: 'inline-flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                fontSize: 12,
                                fontWeight: 700,
                                flexShrink: 0,
                              }}
                            >
                              {index + 1}
                            </Box>
                          </Box>
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" fontWeight={600} sx={{ wordBreak: 'break-word' }}>
                            {subtask.title}
                          </Typography>
                          <Typography variant="caption" color="text.secondary" sx={{ wordBreak: 'break-all' }}>
                            {subtask.task_id}
                          </Typography>
                        </TableCell>
                        <TableCell sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                          {formatSubtaskObjective(subtask)}
                        </TableCell>
                        <TableCell sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                          {formatTaskVerificationMethod(subtask, t)}
                        </TableCell>
                        <TableCell sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                          {formatExecutionParty(subtask, t)}
                        </TableCell>
                        <TableCell>{formatTaskDateTime(taskStartTime(subtask))}</TableCell>
                        <TableCell>{formatTaskDateTime(taskEndTime(subtask))}</TableCell>
                        <TableCell>
                          <StatusChip status={subtask.status} />
                        </TableCell>
                        <TableCell sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                          {formatSubtaskExceptionReason(subtask)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </CardContent>
        </Card>

        {/* Dependencies Card */}
        {(dependencies.length > 0 || dependents.length > 0) && (
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                {t('tasks.dependencies')}
              </Typography>
              
              {dependencies.length > 0 && (
                <Box sx={{ mb: 2 }}>
                  <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                    {t('tasks.preDependencies')}
                  </Typography>
                  <Stack spacing={1}>
                    {dependencies.map((dep) => (
                      <Chip
                        key={dep.task_id}
                        label={`${dep.title} (${formatToken('tasks.statuses', dep.status)})`}
                        onClick={() => handleViewSubtask(dep.task_id)}
                        sx={{ cursor: 'pointer' }}
                      />
                    ))}
                  </Stack>
                </Box>
              )}

              {dependents.length > 0 && (
                <Box>
                  <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                    {t('tasks.postDependencies')}
                  </Typography>
                  <Stack spacing={1}>
                    {dependents.map((dep) => (
                      <Chip
                        key={dep.task_id}
                        label={`${dep.title} (${formatToken('tasks.statuses', dep.status)})`}
                        onClick={() => handleViewSubtask(dep.task_id)}
                        sx={{ cursor: 'pointer' }}
                      />
                    ))}
                  </Stack>
                </Box>
              )}
            </CardContent>
          </Card>
        )}

        {/* Remarks Card */}
        {task.remarks && (
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                {t('tasks.remarks')}
              </Typography>
              <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                {task.remarks}
              </Typography>
            </CardContent>
          </Card>
        )}

        {hasMetadata && (
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                {t('tasks.workflowMetadata')}
              </Typography>
              <Stack spacing={2}>
                {metadataHighlights.length > 0 ? (
                  <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(2, 1fr)' }, gap: 2 }}>
                    {metadataHighlights.map((item) => (
                      <Box key={item.label}>
                        <Typography variant="caption" color="text.secondary">
                          {item.label}
                        </Typography>
                        <Typography variant="body2" sx={{ wordBreak: 'break-word' }}>
                          {item.value}
                        </Typography>
                      </Box>
                    ))}
                  </Box>
                ) : (
                  <Alert severity="info">{t('tasks.noReadableMetadata')}</Alert>
                )}

                {metadataTextItems.length > 0 ? (
                  <Stack spacing={1.5}>
                    {metadataTextItems.map((item) => (
                      <Box key={item.label}>
                        <Typography variant="subtitle2" color="text.secondary">
                          {item.label}
                        </Typography>
                        <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                          {String(item.value)}
                        </Typography>
                      </Box>
                    ))}
                  </Stack>
                ) : null}

                {metadataSections.length > 0 ? (
                  <Box>
                    <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                      {t('tasks.metadataSections')}
                    </Typography>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                      {metadataSections.map((section) => (
                        <Chip
                          key={section.label}
                          label={`${section.label}: ${summarizeNestedValue(section.value, t)}`}
                          variant="outlined"
                          sx={{ maxWidth: '100%', height: 'auto', '& .MuiChip-label': { whiteSpace: 'normal', py: 0.5 } }}
                        />
                      ))}
                    </Stack>
                  </Box>
                ) : null}

                <Accordion disableGutters variant="outlined">
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Typography variant="subtitle2">{t('tasks.rawMetadata')}</Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Box
                      component="pre"
                      sx={{
                        m: 0,
                        p: 2,
                        maxHeight: 360,
                        overflow: 'auto',
                        bgcolor: 'grey.50',
                        borderRadius: 1,
                        fontSize: 12,
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                      }}
                    >
                      {JSON.stringify(task.metadata, null, 2)}
                    </Box>
                  </AccordionDetails>
                </Accordion>
              </Stack>
            </CardContent>
          </Card>
        )}
      </Stack>
    </Box>
  );
};

export default TaskDetailPage;
