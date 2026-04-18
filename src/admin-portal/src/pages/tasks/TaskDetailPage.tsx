import { useTranslation } from 'react-i18next';
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
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
  Tooltip,
} from '@mui/material';
import {
  ArrowBack as BackIcon,
  ContentCopy as CopyIcon,
  Assignment as TaskIcon,
} from '@mui/icons-material';
import { ZentexTask } from './types';
import StatusChip from './TaskStatusChip';

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
          <Button
            variant="outlined"
            startIcon={<BackIcon />}
            onClick={handleBack}
          >
            {t('tasks.backToList')}
          </Button>
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
                    <Tooltip title="复制任务ID">
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

              <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
                <Box>
                  <Typography variant="subtitle2" color="text.secondary">{t('tasks.type')}</Typography>
                  <Typography variant="body1">{task.task_type}</Typography>
                </Box>
                <Box>
                  <Typography variant="subtitle2" color="text.secondary">{t('tasks.priority')}</Typography>
                  <Typography variant="body1">{task.priority || 'medium'}</Typography>
                </Box>
                <Box>
                  <Typography variant="subtitle2" color="text.secondary">{t('tasks.originator')}</Typography>
                  <Typography variant="body1">{task.originator_id}</Typography>
                </Box>
                <Box>
                  <Typography variant="subtitle2" color="text.secondary">{t('tasks.executor')}</Typography>
                  <Typography variant="body1">{task.target_id || t('tasks.unassigned')}</Typography>
                </Box>
                <Box>
                  <Typography variant="subtitle2" color="text.secondary">{t('tasks.createdAt')}</Typography>
                  <Typography variant="body1">
                    {task.created_at ? new Date(task.created_at).toLocaleString('zh-CN') : '-'}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="subtitle2" color="text.secondary">{t('tasks.startedAt')}</Typography>
                  <Typography variant="body1">
                    {task.started_at ? new Date(task.started_at).toLocaleString('zh-CN') : '-'}
                  </Typography>
                </Box>
              </Box>
            </Stack>
          </CardContent>
        </Card>

        {/* Subtasks Card */}
        {subtasks.length > 0 && (
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                {t('tasks.subtasks')} ({statistics.total_subtasks})
              </Typography>
              
              <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, 1fr)', md: 'repeat(4, 1fr)' }, gap: 2, mb: 2 }}>
                <Chip label={`${t('tasks.completed')}: ${statistics.completed_subtasks}`} color="success" size="small" />
                <Chip label={`${t('tasks.inProgress')}: ${statistics.in_progress_subtasks}`} color="primary" size="small" />
                <Chip label={`${t('tasks.pending')}: ${statistics.pending_subtasks}`} color="warning" size="small" />
                <Chip label={`${t('tasks.failed')}: ${statistics.failed_subtasks}`} color="error" size="small" />
              </Box>

              <Stack spacing={1}>
                {subtasks.map((subtask) => (
                  <Card key={subtask.task_id} variant="outlined" sx={{ cursor: 'pointer' }} onClick={() => handleViewSubtask(subtask.task_id)}>
                    <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
                      <Stack direction="row" justifyContent="space-between" alignItems="center">
                        <Box>
                          <Typography variant="body2" fontWeight="bold">
                            {subtask.title}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {subtask.task_id}
                          </Typography>
                        </Box>
                        <StatusChip status={subtask.status} />
                      </Stack>
                    </CardContent>
                  </Card>
                ))}
              </Stack>
            </CardContent>
          </Card>
        )}

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
                        label={`${dep.title} (${dep.status})`}
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
                        label={`${dep.title} (${dep.status})`}
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

        {task.metadata && Object.keys(task.metadata).length > 0 && (
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                {t('tasks.workflowMetadata')}
              </Typography>
              <Stack spacing={1}>
                <Typography variant="body2">
                  <strong>{t('tasks.sourceModule')}:</strong> {String(task.metadata.source_module || '--')}
                </Typography>
                <Typography variant="body2">
                  <strong>{t('tasks.workflowStatus')}:</strong> {String(task.metadata.workflow_status || '--')}
                </Typography>
                <Typography variant="body2">
                  <strong>{t('tasks.workflowProgress')}:</strong> {String(task.metadata.workflow_progress ?? '--')}
                </Typography>
                <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                  <strong>{t('tasks.rawMetadata')}:</strong> {JSON.stringify(task.metadata, null, 2)}
                </Typography>
              </Stack>
            </CardContent>
          </Card>
        )}
      </Stack>
    </Box>
  );
};

export default TaskDetailPage;
