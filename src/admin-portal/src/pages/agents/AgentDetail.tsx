import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Chip,
  Button,
  Tabs,
  Tab,
  Alert,
  CircularProgress,
  Stack,
  Divider,
  LinearProgress,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  TextField,
  MenuItem,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  Tooltip,
} from '@mui/material';
import { DataGrid, GridColDef, GridRenderCellParams } from '@mui/x-data-grid';
import {
  ArrowBack as ArrowBackIcon,
  Refresh as RefreshIcon,
  ExpandMore as ExpandMoreIcon,
  Cancel as CancelIcon,
  Replay as ReplayIcon,
  FilterList as FilterListIcon,
  Search as SearchIcon,
  PowerSettingsNew as PowerSettingsNewIcon,
  Block as BlockIcon,
  DeleteOutline as DeleteOutlineIcon,
} from '@mui/icons-material';

type AgentStatus = 'idle' | 'active' | 'busy' | 'offline' | 'handshake_failed' | 'audit_failed' | 'invocation_blocked';
type TrustLevel = 'unknown' | 'pending' | 'trusted' | 'restricted' | 'revoked';

interface CreditScoreDimension {
  name: string;
  name_en: string;
  score: number;
  weight: number;
  description: string;
  trend: 'up' | 'down' | 'stable';
}

interface CreditScore {
  total_score: number;
  dimensions: CreditScoreDimension[];
  history: any[];
  error?: string;
}

interface AgentStatistics {
  total_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  in_progress_tasks: number;
  pending_tasks: number;
  avg_completion_time: number;
  uptime_percentage: number;
  error?: string;
}

interface AgentDetail {
  agent_id: string;
  name: string;
  agent_name: string;
  version: string;
  function_description: string;
  endpoint: string;
  role_tag: string;
  trust_level: TrustLevel;
  status: AgentStatus;
  scope: string[];
  capabilities: any[];
  latency_ms: number | null;
  success_rate: number;
  last_ping_at: string | null;
  registered_at: string;
  assigned_goal: string | null;
  inbox: any[];
  receipts: any[];
  credit_score: CreditScore;
  statistics: AgentStatistics;
}

interface TaskItem {
  id: string;
  task_id: string;
  subtask_id: string | null;
  title: string;
  task_type: string;
  status: string;
  progress: number;
  originator_id: string;
  remarks: string | null;
  started_at: string | null;
  completed_at: string | null;
  estimated_completion: string | null;
  priority: string;
}

interface AdvancedFilters {
  search: string;
  taskType: string;
  originator: string;
  dateFrom: string;
  dateTo: string;
}

interface TasksResponse {
  tasks: TaskItem[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
  };
}

const StatusChip = ({ status }: { status: AgentStatus }) => {
  const { t } = useTranslation();
  const labelMap: Record<AgentStatus, string> = {
    idle: t("agents.status.idle"),
    active: t("agents.status.active"),
    busy: t("agents.status.busy"),
    offline: t("agents.status.offline"),
    handshake_failed: t("agents.status.handshakeFailed"),
    audit_failed: t("agents.status.auditFailed"),
    invocation_blocked: t("agents.status.invocationBlocked"),
  };

  return (
    <Chip
      label={labelMap[status]}
      color={status === 'idle' ? 'success' : status === 'active' ? 'primary' : status === 'busy' ? 'warning' : status === 'offline' ? 'default' : 'error'}
      variant="filled"
      size="small"
      sx={{ fontWeight: 'bold' }}
    />
  );
};

const TrustLevelChip = ({ level }: { level: TrustLevel }) => {
  return (
    <Chip
      label={level.toUpperCase()}
      color={level === 'trusted' ? 'success' : level === 'pending' ? 'warning' : level === 'restricted' ? 'info' : level === 'revoked' ? 'error' : 'default'}
      variant={level === 'pending' ? 'outlined' : 'filled'}
      size="small"
      sx={{ fontWeight: 'bold' }}
    />
  );
};

const CreditScoreGauge = ({ score }: { score: number }) => {
  const { t } = useTranslation();
  const getColor = (s: number) => {
    if (s >= 90) return 'success';
    if (s >= 70) return 'primary';
    if (s >= 50) return 'warning';
    return 'error';
  };

  return (
    <Box sx={{ textAlign: 'center', py: 2 }}>
      <Typography variant="h2" color={getColor(score)} fontWeight="bold">
        {score.toFixed(1)}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {t("agents.creditScore.total")}
      </Typography>
      <LinearProgress
        variant="determinate"
        value={score}
        color={getColor(score)}
        sx={{ mt: 2, height: 8, borderRadius: 4 }}
      />
    </Box>
  );
};

const TASK_COLUMNS: (
  handleCancel: (id: string, title: string) => void,
  handleRetry: (id: string, title: string) => void,
  t: (key: string) => string,
  locale: string,
) => GridColDef[] =
  (handleCancel, handleRetry, t, locale) => [
  { field: 'task_id', headerName: t("agents.tasks.taskId"), width: 120 },
  { field: 'title', headerName: t("agents.tasks.taskName"), width: 200, flex: 1 },
  { 
    field: 'status', 
    headerName: t("common.status"), 
    width: 130,
    renderCell: (params: GridRenderCellParams) => {
      const statusColors: Record<string, any> = {
        in_progress: 'primary',
        todo: 'default',
        blocked: 'warning',
        waiting_confirmation: 'secondary',
        done: 'success',
        failed: 'error',
        cancelled: 'default',
      };
      return (
        <Chip
          label={String(params.value || '').toUpperCase()}
          size="small"
          color={statusColors[String(params.value)] || 'default'}
          variant="outlined"
        />
      );
    }
  },
  { 
    field: 'progress', 
    headerName: t("agents.tasks.progress"), 
    width: 150,
    renderCell: (params: GridRenderCellParams) => (
      <Box sx={{ width: '100%' }}>
        <LinearProgress 
          variant="determinate" 
          value={(params.value || 0) * 100} 
          sx={{ height: 6, borderRadius: 3 }} 
        />
        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
          {Math.round((params.value || 0) * 100)}%
        </Typography>
      </Box>
    )
  },
  { field: 'originator_id', headerName: t("agents.tasks.originator"), width: 130 },
  { 
    field: 'started_at', 
    headerName: t("agents.tasks.startTime"), 
    width: 180,
    valueFormatter: (params: any) => params.value ? new Date(params.value).toLocaleString(locale) : '-'
  },
  { 
    field: 'completed_at', 
    headerName: t("agents.tasks.completionTime"), 
    width: 180,
    valueFormatter: (params: any) => params.value ? new Date(params.value).toLocaleString(locale) : '-'
  },
  {
    field: 'actions',
    headerName: t("common.actions"),
    width: 150,
    sortable: false,
    renderCell: (params: GridRenderCellParams) => {
      const canCancel = ['todo', 'in_progress', 'blocked', 'waiting_confirmation'].includes(params.row.status);
      const canRetry = params.row.status === 'failed';
      
      return (
        <Stack direction="row" spacing={1}>
          {canCancel && (
            <Tooltip title={t("agents.tasks.cancelTask")}>
              <IconButton
                size="small"
                color="warning"
                onClick={() => handleCancel(params.row.task_id, params.row.title)}
              >
                <CancelIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          {canRetry && (
            <Tooltip title={t("agents.tasks.retryTask")}>
              <IconButton
                size="small"
                color="primary"
                onClick={() => handleRetry(params.row.task_id, params.row.title)}
              >
                <ReplayIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
        </Stack>
      );
    }
  },
];

export default function AgentDetail() {
  const { t, i18n } = useTranslation();
  const { agentId } = useParams<{ agentId: string }>();
  const navigate = useNavigate();
  const locale = i18n.language || "zh-CN";
  
  const [agent, setAgent] = useState<AgentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tabValue, setTabValue] = useState(0);
  
  const [inProgressTasks, setInProgressTasks] = useState<TaskItem[]>([]);
  const [pendingTasks, setPendingTasks] = useState<TaskItem[]>([]);
  const [failedTasks, setFailedTasks] = useState<TaskItem[]>([]);
  const [historyTasks, setHistoryTasks] = useState<TaskItem[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  
  // Advanced filter state
  const [showFilters, setShowFilters] = useState(false);
  const [advancedFilters, setAdvancedFilters] = useState<AdvancedFilters>({
    search: '',
    taskType: '',
    originator: '',
    dateFrom: '',
    dateTo: '',
  });
  
  // Action dialog state
  const [actionDialog, setActionDialog] = useState<{
    open: boolean;
    type: 'cancel' | 'retry';
    taskId: string;
    taskTitle: string;
  }>({ open: false, type: 'cancel', taskId: '', taskTitle: '' });
  const [actionLoading, setActionLoading] = useState(false);
  const [deletingAgent, setDeletingAgent] = useState(false);

  const fetchAgentDetail = async () => {
    if (!agentId) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const res = await fetch(`/api/web/agents/${agentId}/detail`);
      if (!res.ok) {
        throw new Error(t("agents.errors.fetchDetailFailed", { status: res.status }));
      }
      const data = await res.json();
      setAgent(data);
    } catch (err) {
      console.error('Failed to fetch agent detail', err);
      setError(err instanceof Error ? err.message : t("agents.errors.fetchDetailFailed"));
    } finally {
      setLoading(false);
    }
  };

  const fetchTasksByStatus = async (statusFilter: string, tabName: string) => {
    if (!agentId) return;
    
    try {
      // Build query params
      const params = new URLSearchParams({
        status: statusFilter,
        page: '1',
        page_size: '100',
      });
      
      // Add advanced filters if present
      if (advancedFilters.search) {
        params.append('search', advancedFilters.search);
      }
      if (advancedFilters.taskType) {
        params.append('task_type', advancedFilters.taskType);
      }
      if (advancedFilters.originator) {
        params.append('originator', advancedFilters.originator);
      }
      if (advancedFilters.dateFrom) {
        params.append('date_from', advancedFilters.dateFrom);
      }
      if (advancedFilters.dateTo) {
        params.append('date_to', advancedFilters.dateTo);
      }
      
      const res = await fetch(
        `/api/web/agents/${agentId}/tasks/by-status?${params.toString()}`
      );
      if (!res.ok) {
        throw new Error(t("agents.errors.fetchTasksFailed"));
      }
      const data: TasksResponse = await res.json();
      
      switch (tabName) {
        case 'inProgress':
          setInProgressTasks(data.tasks.map(t => ({ ...t, id: t.task_id })));
          break;
        case 'pending':
          setPendingTasks(data.tasks.map(t => ({ ...t, id: t.task_id })));
          break;
        case 'failed':
          setFailedTasks(data.tasks.map(t => ({ ...t, id: t.task_id })));
          break;
        case 'history':
          setHistoryTasks(data.tasks.map(t => ({ ...t, id: t.task_id })));
          break;
      }
    } catch (err) {
      console.error(`Failed to fetch ${tabName} tasks`, err);
    }
  };

  const fetchAllTasks = async () => {
    setTasksLoading(true);
    await Promise.all([
      fetchTasksByStatus('in_progress', 'inProgress'),
      fetchTasksByStatus('todo,blocked,waiting_confirmation', 'pending'),
      fetchTasksByStatus('failed', 'failed'),
      fetchTasksByStatus('done,cancelled', 'history'),
    ]);
    setTasksLoading(false);
  };

  useEffect(() => {
    fetchAgentDetail();
  }, [agentId]);

  useEffect(() => {
    if (agent) {
      fetchAllTasks();
    }
  }, [agent, advancedFilters]); // Re-fetch when filters change

  // Task action handlers
  const handleCancelTask = async (taskId: string, taskTitle: string) => {
    setActionDialog({ open: true, type: 'cancel', taskId, taskTitle });
  };

  const handleRetryTask = async (taskId: string, taskTitle: string) => {
    setActionDialog({ open: true, type: 'retry', taskId, taskTitle });
  };

  const confirmAction = async () => {
    if (!agentId) return;
    
    setActionLoading(true);
    try {
      const endpoint = actionDialog.type === 'cancel' 
        ? `/api/web/agents/${agentId}/tasks/${actionDialog.taskId}/cancel`
        : `/api/web/agents/${agentId}/tasks/${actionDialog.taskId}/retry`;
      
      const res = await fetch(endpoint, { method: 'POST' });
      
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || t("agents.errors.actionFailed"));
      }
      
      // Refresh tasks after successful action
      await fetchAllTasks();
      
      // Show success message
      alert(actionDialog.type === 'cancel' 
        ? t("agents.tasks.cancelSuccess", { title: actionDialog.taskTitle })
        : t("agents.tasks.retrySuccess", { title: actionDialog.taskTitle })
      );
    } catch (err) {
      console.error('Task action failed', err);
      alert(err instanceof Error ? err.message : t("agents.errors.actionFailed"));
    } finally {
      setActionLoading(false);
      setActionDialog({ open: false, type: 'cancel', taskId: '', taskTitle: '' });
    }
  };

  const updateAgentActivation = async (action: 'activate' | 'disable') => {
    if (!agentId) return;
    try {
      const res = await fetch(`/api/web/agents/${agentId}/${action}`, { method: 'POST' });
      const payload = await res.json();
      if (!res.ok) {
        throw new Error(payload?.detail || `${action} failed`);
      }
      await fetchAgentDetail();
      await fetchAllTasks();
    } catch (err) {
      setError(err instanceof Error ? err.message : `${action} failed`);
    }
  };

  const deleteAgentRegistration = async () => {
    if (!agent || !agentId) return;
    const displayName = agent.agent_name || agent.name || agent.agent_id;
    if (!window.confirm(t("agents.deleteConfirm", { name: displayName }))) {
      return;
    }

    setDeletingAgent(true);
    setError(null);
    try {
      const res = await fetch(`/api/web/agents/${encodeURIComponent(agentId)}`, { method: 'DELETE' });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = payload?.detail;
        const message =
          typeof detail === 'string' ? detail : detail?.operator_message || detail?.message || t("agents.deleteFailed");
        throw new Error(message);
      }
      navigate('/console/agents');
    } catch (err) {
      setError(err instanceof Error ? err.message : t("agents.deleteFailed"));
    } finally {
      setDeletingAgent(false);
    }
  };

  const clearFilters = () => {
    setAdvancedFilters({
      search: '',
      taskType: '',
      originator: '',
      dateFrom: '',
      dateTo: '',
    });
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error || !agent) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error" sx={{ mb: 2 }}>
          {error || t("agents.errors.agentNotFound")}
        </Alert>
        <Button startIcon={<ArrowBackIcon />} onClick={() => navigate('/console/agents')}>
          {t("agents.backToList")}
        </Button>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={3}>
        {/* Header */}
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Stack direction="row" spacing={2} alignItems="center">
            <Button
              startIcon={<ArrowBackIcon />}
              onClick={() => navigate('/console/agents')}
              variant="outlined"
            >
              {t("agents.backToList")}
            </Button>
            <Box>
              <Typography variant="h4" component="h1" gutterBottom>
                {agent.agent_name}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                ID: {agent.agent_id} | {t("agents.version")}: v{agent.version}
              </Typography>
            </Box>
          </Stack>
          <Stack direction="row" spacing={1}>
            <Button startIcon={<PowerSettingsNewIcon />} onClick={() => void updateAgentActivation('activate')} variant="outlined">
              激活
            </Button>
            <Button startIcon={<BlockIcon />} onClick={() => void updateAgentActivation('disable')} variant="outlined">
              关闭
            </Button>
            <Button
              color="error"
              disabled={deletingAgent}
              startIcon={<DeleteOutlineIcon />}
              onClick={() => void deleteAgentRegistration()}
              variant="outlined"
            >
              {t("agents.delete")}
            </Button>
            <Button
              startIcon={<RefreshIcon />}
              onClick={() => {
                fetchAgentDetail();
                fetchAllTasks();
              }}
              variant="contained"
            >
              {t("common.refresh")}
            </Button>
          </Stack>
        </Stack>

        {/* Basic Info & Status */}
        <Paper sx={{ p: 3 }}>
          <Grid container spacing={3}>
            <Grid size={12}>
              <Stack direction="row" spacing={2} alignItems="center">
                <StatusChip status={agent.status} />
                <TrustLevelChip level={agent.trust_level} />
                <Chip label={agent.role_tag} variant="outlined" size="small" />
              </Stack>
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                {t("agents.functionDescription")}
              </Typography>
              <Typography variant="body1">{agent.function_description}</Typography>
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                {t("agents.assignedGoal")}
              </Typography>
              <Typography variant="body1" color="primary">
                {agent.assigned_goal || t("agents.none")}
              </Typography>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Typography variant="caption" color="text.secondary">Endpoint</Typography>
              <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>
                {agent.endpoint}
              </Typography>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Typography variant="caption" color="text.secondary">{t("agents.registeredAt")}</Typography>
              <Typography variant="body2">
                {new Date(agent.registered_at).toLocaleString(locale)}
              </Typography>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Typography variant="caption" color="text.secondary">{t("agents.lastActive")}</Typography>
              <Typography variant="body2">
                {agent.last_ping_at ? new Date(agent.last_ping_at).toLocaleString(locale) : t("agents.unknown")}
              </Typography>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Typography variant="caption" color="text.secondary">{t("agents.successRate")}</Typography>
              <Typography variant="body2" color="success.main" fontWeight="bold">
                {(agent.success_rate * 100).toFixed(1)}%
              </Typography>
            </Grid>
          </Grid>
        </Paper>

        {/* Credit Score Section */}
        <Paper sx={{ p: 3 }}>
          <Typography variant="h6" gutterBottom fontWeight="bold">
            {t("agents.creditScore.title")}
          </Typography>
          <Divider sx={{ mb: 3 }} />
          
          <Grid container spacing={4}>
            <Grid size={{ xs: 12, md: 4 }}>
              <CreditScoreGauge score={agent.credit_score.total_score} />
            </Grid>
            <Grid size={{ xs: 12, md: 8 }}>
              <Stack spacing={2}>
                {agent.credit_score.dimensions.map((dim, idx) => (
                  <Accordion key={idx} defaultExpanded={idx < 2}>
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', width: '100%', alignItems: 'center' }}>
                        <Typography fontWeight="bold">{dim.name}</Typography>
                        <Stack direction="row" spacing={2} alignItems="center">
                          <Typography variant="body2" color="text.secondary">
                            {t("agents.creditScore.weight")}: {(dim.weight * 100).toFixed(0)}%
                          </Typography>
                          <Chip
                            label={dim.score.toFixed(1)}
                            size="small"
                            color={dim.score >= 80 ? 'success' : dim.score >= 60 ? 'warning' : 'error'}
                          />
                        </Stack>
                      </Box>
                    </AccordionSummary>
                    <AccordionDetails>
                      <Typography variant="body2" color="text.secondary" paragraph>
                        {dim.description}
                      </Typography>
                      <LinearProgress
                        variant="determinate"
                        value={dim.score}
                        color={dim.score >= 80 ? 'success' : dim.score >= 60 ? 'warning' : 'error'}
                        sx={{ height: 6, borderRadius: 3 }}
                      />
                    </AccordionDetails>
                  </Accordion>
                ))}
              </Stack>
            </Grid>
          </Grid>
        </Paper>

        {/* Statistics Summary */}
        <Paper sx={{ p: 3 }}>
          <Typography variant="h6" gutterBottom fontWeight="bold">
            {t("agents.statistics.title")}
          </Typography>
          <Divider sx={{ mb: 2 }} />
          <Grid container spacing={2}>
            <Grid size={{ xs: 6, sm: 3, md: 2 }}>
              <Typography variant="caption" color="text.secondary">{t("agents.statistics.totalTasks")}</Typography>
              <Typography variant="h5">{agent.statistics.total_tasks}</Typography>
            </Grid>
            <Grid size={{ xs: 6, sm: 3, md: 2 }}>
              <Typography variant="caption" color="text.secondary">{t("agents.statistics.completed")}</Typography>
              <Typography variant="h5" color="success.main">{agent.statistics.completed_tasks}</Typography>
            </Grid>
            <Grid size={{ xs: 6, sm: 3, md: 2 }}>
              <Typography variant="caption" color="text.secondary">{t("agents.statistics.inProgress")}</Typography>
              <Typography variant="h5" color="primary.main">{agent.statistics.in_progress_tasks}</Typography>
            </Grid>
            <Grid size={{ xs: 6, sm: 3, md: 2 }}>
              <Typography variant="caption" color="text.secondary">{t("agents.statistics.pending")}</Typography>
              <Typography variant="h5" color="warning.main">{agent.statistics.pending_tasks}</Typography>
            </Grid>
            <Grid size={{ xs: 6, sm: 3, md: 2 }}>
              <Typography variant="caption" color="text.secondary">{t("agents.statistics.failed")}</Typography>
              <Typography variant="h5" color="error.main">{agent.statistics.failed_tasks}</Typography>
            </Grid>
            <Grid size={{ xs: 6, sm: 3, md: 2 }}>
              <Typography variant="caption" color="text.secondary">{t("agents.statistics.avgTime")}</Typography>
              <Typography variant="h6">
                {agent.statistics.avg_completion_time > 0 
                  ? `${(agent.statistics.avg_completion_time / 60).toFixed(1)}${t("common.minutes")}`
                  : '-'}
              </Typography>
            </Grid>
          </Grid>
        </Paper>

        {/* Tasks Tabs */}
        <Paper sx={{ p: 3 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
            <Typography variant="h6" fontWeight="bold">
              {t("agents.tasks.management")}
            </Typography>
            <Button
              startIcon={<FilterListIcon />}
              onClick={() => setShowFilters(!showFilters)}
              variant={showFilters ? "contained" : "outlined"}
              size="small"
            >
              {showFilters ? t("agents.tasks.hideFilters") : t("agents.tasks.advancedFilters")}
            </Button>
          </Stack>
          
          {/* Advanced Filters */}
          {showFilters && (
            <Box sx={{ mb: 3, p: 2, bgcolor: 'action.hover', borderRadius: 1 }}>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, md: 4 }}>
                  <TextField
                    fullWidth
                    size="small"
                    label={t("agents.tasks.searchTask")}
                    placeholder={t("agents.tasks.searchPlaceholder")}
                    value={advancedFilters.search}
                    onChange={(e) => setAdvancedFilters({ ...advancedFilters, search: e.target.value })}
                    InputProps={{
                      startAdornment: <SearchIcon sx={{ mr: 1, color: 'text.secondary' }} />,
                    }}
                  />
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 2 }}>
                  <TextField
                    fullWidth
                    size="small"
                    select
                    label={t("agents.tasks.taskType")}
                    value={advancedFilters.taskType}
                    onChange={(e) => setAdvancedFilters({ ...advancedFilters, taskType: e.target.value })}
                  >
                    <MenuItem value="">{t("common.all")}</MenuItem>
                    <MenuItem value="data_processing">{t("agents.tasks.types.dataProcessing")}</MenuItem>
                    <MenuItem value="analysis">{t("agents.tasks.types.analysis")}</MenuItem>
                    <MenuItem value="generation">{t("agents.tasks.types.generation")}</MenuItem>
                    <MenuItem value="validation">{t("agents.tasks.types.validation")}</MenuItem>
                  </TextField>
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 2 }}>
                  <TextField
                    fullWidth
                    size="small"
                    label={t("agents.tasks.originator")}
                    placeholder="Originator ID"
                    value={advancedFilters.originator}
                    onChange={(e) => setAdvancedFilters({ ...advancedFilters, originator: e.target.value })}
                  />
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 2 }}>
                  <TextField
                    fullWidth
                    size="small"
                    label={t("agents.tasks.startDate")}
                    type="date"
                    value={advancedFilters.dateFrom}
                    onChange={(e) => setAdvancedFilters({ ...advancedFilters, dateFrom: e.target.value })}
                    InputLabelProps={{ shrink: true }}
                  />
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 2 }}>
                  <TextField
                    fullWidth
                    size="small"
                    label={t("agents.tasks.endDate")}
                    type="date"
                    value={advancedFilters.dateTo}
                    onChange={(e) => setAdvancedFilters({ ...advancedFilters, dateTo: e.target.value })}
                    InputLabelProps={{ shrink: true }}
                  />
                </Grid>
                <Grid size={{ xs: 12, md: 12 }}>
                  <Stack direction="row" spacing={1} justifyContent="flex-end">
                    <Button
                      size="small"
                      onClick={clearFilters}
                      disabled={!advancedFilters.search && !advancedFilters.taskType && !advancedFilters.originator && !advancedFilters.dateFrom && !advancedFilters.dateTo}
                    >
                      {t("agents.tasks.clearFilters")}
                    </Button>
                  </Stack>
                </Grid>
              </Grid>
            </Box>
          )}
          
          <Divider sx={{ mb: 2 }} />
          
          <Tabs value={tabValue} onChange={(_, v) => setTabValue(v)} sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
            <Tab label={`${t("agents.tabs.inProgress")} (${inProgressTasks.length})`} />
            <Tab label={`${t("agents.tabs.pending")} (${pendingTasks.length})`} />
            <Tab label={`${t("agents.tabs.failed")} (${failedTasks.length})`} />
            <Tab label={`${t("agents.tabs.history")} (${historyTasks.length})`} />
          </Tabs>

          {tasksLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
              <CircularProgress />
            </Box>
          ) : (
            <Box sx={{ height: 500, width: '100%' }}>
              <DataGrid
                rows={
                  tabValue === 0 ? inProgressTasks :
                  tabValue === 1 ? pendingTasks :
                  tabValue === 2 ? failedTasks :
                  historyTasks
                }
                columns={TASK_COLUMNS(handleCancelTask, handleRetryTask, t, locale)}
                pageSizeOptions={[10, 20, 50]}
                initialState={{
                  pagination: { paginationModel: { pageSize: 10 } },
                }}
                disableRowSelectionOnClick
                localeText={{
                  noRowsLabel: t("agents.tasks.noData"),
                }}
              />
            </Box>
          )}
        </Paper>
      </Stack>

      {/* Action Confirmation Dialog */}
      <Dialog
        open={actionDialog.open}
        onClose={() => !actionLoading && setActionDialog({ open: false, type: 'cancel', taskId: '', taskTitle: '' })}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          {actionDialog.type === 'cancel' ? t("agents.dialogs.confirmCancel") : t("agents.dialogs.confirmRetry")}
        </DialogTitle>
        <DialogContent>
          <Typography variant="body1" sx={{ mb: 2 }}>
            {actionDialog.type === 'cancel' 
              ? t("agents.dialogs.cancelMessage", { title: actionDialog.taskTitle })
              : t("agents.dialogs.retryMessage", { title: actionDialog.taskTitle })
            }
          </Typography>
          <Alert severity={actionDialog.type === 'cancel' ? 'warning' : 'info'}>
            {actionDialog.type === 'cancel'
              ? t("agents.dialogs.cancelWarning")
              : t("agents.dialogs.retryInfo")
            }
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button 
            onClick={() => setActionDialog({ open: false, type: 'cancel', taskId: '', taskTitle: '' })}
            disabled={actionLoading}
          >
            {t("common.cancel")}
          </Button>
          <Button 
            onClick={confirmAction}
            variant="contained"
            color={actionDialog.type === 'cancel' ? 'warning' : 'primary'}
            disabled={actionLoading}
            startIcon={actionLoading ? <CircularProgress size={20} /> : (actionDialog.type === 'cancel' ? <CancelIcon /> : <ReplayIcon />)}
          >
            {actionLoading ? t("common.processing") : (actionDialog.type === 'cancel' ? t("agents.dialogs.confirmCancelBtn") : t("agents.dialogs.confirmRetryBtn"))}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
