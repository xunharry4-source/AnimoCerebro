import React from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Button,
  Tabs,
  Tab,
  Badge,
  Stack,
  Alert,
  Card,
  CardContent,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from '@mui/material';
import {
  AccountTree as WorkflowIcon,
  Assignment as TaskIcon,
  Article as LogsIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import { DataGrid, GridColDef } from '@mui/x-data-grid';

// Import modular components
import useTaskManagement from './useTaskManagement';
import StatusChip from './TaskStatusChip';
import TaskTabPanel from './TaskTabPanel';
import { ZentexTask } from './types';
import { formatTaskDateTime } from './taskDisplay';

const TASK_SOURCE_FILTERS = ['nine_questions', 'nine_questions.q8', 'nine_questions.q9', 'reflection', 'learning', 'upgrade', 'manual'];
const taskSourceModuleLabelKey = (source: string) => `tasks.sourceModules.${source.replace(/\./g, '_')}`;
const EMPTY_VALUE = '-';

const ZentexTaskManager: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const {
    currentRows,
    rowCount,
    groupCounts,
    paginationModel,
    setPaginationModel,
    loading,
    error,
    fetchTasks,
    tabValue,
    setTabValue,
    sourceModuleFilter,
    setSourceModuleFilter,
  } = useTaskManagement();

  const TABS = [
    { label: t('tasks.allStatuses'), key: 'all' },
    { label: t('tasks.inProgress'), key: 'in_progress' },
    { label: t('tasks.statuses.todo'), key: 'todo' },
    { label: t('tasks.statuses.blocked'), key: 'blocked' },
    { label: t('tasks.waitingConfirmation'), key: 'waiting_confirmation' },
    { label: t('tasks.completed'), key: 'completed' },
    { label: t('tasks.failed'), key: 'failed' },
    { label: t('tasks.statuses.suspended'), key: 'suspended' },
    { label: t('tasks.statuses.archived'), key: 'archived' },
    { label: t('tasks.cancelled'), key: 'cancelled' },
  ];

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const handleViewDetail = (task: ZentexTask) => {
    navigate(`/console/tasks/${task.task_id}`);
  };

  const handleViewWorkflow = (task: ZentexTask) => {
    navigate(`/console/tasks/${task.task_id}/workflow`);
  };

  const handleViewLogs = () => {
    navigate('/console/module-logs/tasks');
  };

  const formatSourceValue = (source?: string | null) => {
    if (!source) {
      return EMPTY_VALUE;
    }
    return t(taskSourceModuleLabelKey(String(source)), { defaultValue: String(source).replace(/[_-]/g, ' ') });
  };

  const formatSourceModule = (task: ZentexTask) => {
    const source = task.metadata?.source_module || task.metadata?.source || task.originator_id || 'core';
    const parentSource = task.metadata?.parent_source_module;
    const sourceLabel = formatSourceValue(String(source));
    if (parentSource && parentSource !== source) {
      return `${sourceLabel} / ${formatSourceValue(String(parentSource))}`;
    }
    return sourceLabel;
  };

  const formatTaskObjective = (task: ZentexTask) => {
    const metadata = task.metadata || {};
    const q9Blueprint = metadata.q9_action_blueprint || metadata.q9_action_plan || {};
    const q8Task = metadata.q9_q8_task || {};
    return (
      metadata.objective ||
      metadata.intent_objective ||
      q9Blueprint.plan_objective ||
      q8Task.intent_objective ||
      metadata.summary ||
      metadata.description ||
      task.remarks ||
      EMPTY_VALUE
    );
  };

  const formatTriggerEvent = (task: ZentexTask) => {
    const metadata = task.metadata || {};
    return (
      metadata.trigger_event ||
      metadata.event ||
      metadata.event_type ||
      metadata.workflow_event_type ||
      metadata.trigger ||
      metadata.creation_reason ||
      metadata.source_chain ||
      EMPTY_VALUE
    );
  };

  const columns: GridColDef[] = [
    { field: 'task_id', headerName: t('tasks.taskId'), width: 120 },
    { field: 'title', headerName: t('tasks.title'), flex: 1, minWidth: 220 },
    {
      field: 'created_at',
      headerName: t('tasks.createdAt'),
      width: 180,
      valueGetter: (_value, row: ZentexTask) => formatTaskDateTime(row.created_at),
    },
    {
      field: 'objective',
      headerName: t('tasks.metadataFields.objective'),
      flex: 1.3,
      minWidth: 280,
      valueGetter: (_value, row: ZentexTask) => formatTaskObjective(row),
    },
    {
      field: 'source_module',
      headerName: t('tasks.sourceModule'),
      width: 180,
      valueGetter: (_value, row: ZentexTask) => formatSourceModule(row),
    },
    {
      field: 'trigger_event',
      headerName: t('tasks.triggerEvent', { defaultValue: '任务触发事件' }),
      flex: 1,
      minWidth: 220,
      valueGetter: (_value, row: ZentexTask) => formatTriggerEvent(row),
    },
    {
      field: 'status',
      headerName: t('tasks.status'),
      width: 130,
      renderCell: (params) => <StatusChip status={params.value} />,
    },
    {
      field: 'actions',
      headerName: t('tasks.actions'),
      width: 220,
      sortable: false,
      renderCell: (params) => (
        <Stack direction="row" spacing={1} alignItems="center">
          <Button size="small" variant="outlined" onClick={() => handleViewDetail(params.row)}>
            {t('tasks.view', { defaultValue: '查看' })}
          </Button>
          <Button
            size="small"
            variant="outlined"
            startIcon={<WorkflowIcon />}
            onClick={() => handleViewWorkflow(params.row)}
          >
            {t('tasks.viewWorkflow')}
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={3}>
        {/* Header Section */}
        <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
          <Box>
            <Typography variant="h4" component="h1" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <TaskIcon color="primary" fontSize="large" />
              Zentex {t('tasks.managementCenter')}
            </Typography>
            <Typography variant="body1" color="text.secondary">
              {t('tasks.multiTabView')}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1}>
            <Button
              startIcon={<LogsIcon />}
              onClick={handleViewLogs}
              variant="outlined"
            >
              {t('tasks.logs.viewModuleLogs')}
            </Button>
            <Button 
              startIcon={<RefreshIcon />} 
              onClick={fetchTasks} 
              variant="outlined"
              disabled={loading}
            >
              {loading ? t('common.refreshing') : t('common.refresh')}
            </Button>
          </Stack>
        </Stack>

        <FormControl sx={{ width: { xs: '100%', sm: 260 } }}>
          <InputLabel id="task-source-module-filter-label">{t('tasks.sourceModuleFilter')}</InputLabel>
          <Select
            labelId="task-source-module-filter-label"
            aria-label={t('tasks.sourceModuleFilter')}
            value={sourceModuleFilter}
            label={t('tasks.sourceModuleFilter')}
            onChange={(event) => setSourceModuleFilter(String(event.target.value))}
          >
            <MenuItem value="all">{t('tasks.allSourceModules')}</MenuItem>
            {TASK_SOURCE_FILTERS.map((source) => (
              <MenuItem key={source} value={source}>
                {t(taskSourceModuleLabelKey(source))}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        {/* Error Alert */}
        {error && (
          <Alert severity="error" data-testid="task-list-error">
            {error}
          </Alert>
        )}

        {/* Tabs Navigation */}
        <Card>
          <CardContent sx={{ pb: 0 }}>
            <Tabs
              value={tabValue}
              onChange={handleTabChange}
              aria-label="task status tabs"
              variant="scrollable"
              scrollButtons="auto"
            >
              {TABS.map((tab, index) => {
                const count = groupCounts[tab.key as keyof typeof groupCounts] || 0;
                return (
                  <Tab
                    key={tab.key}
                    label={
                      <Badge badgeContent={count} color="primary">
                        {tab.label}
                      </Badge>
                    }
                    id={`task-tab-${index}`}
                    aria-controls={`task-tabpanel-${index}`}
                  />
                );
              })}
            </Tabs>
          </CardContent>
        </Card>

        {/* Task List */}
        {TABS.map((tab, index) => (
          <TaskTabPanel key={tab.key} value={tabValue} index={index}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  {tab.label}
                </Typography>
                <Box sx={{ height: 600, width: '100%' }}>
                  <DataGrid
                    rows={currentRows}
                    columns={columns}
                    loading={loading}
                    getRowId={(row) => row.task_id}
                    pageSizeOptions={[10, 25, 50]}
                    paginationMode="server"
                    paginationModel={paginationModel}
                    onPaginationModelChange={setPaginationModel}
                    rowCount={rowCount}
                    disableRowSelectionOnClick
                    localeText={{
                      noRowsLabel: t('tasks.noData'),
                      toolbarDensity: t('tasks.density'),
                      toolbarFilters: t('tasks.filters'),
                      toolbarColumns: t('tasks.columns'),
                    }}
                  />
                </Box>
              </CardContent>
            </Card>
          </TaskTabPanel>
        ))}
      </Stack>
    </Box>
  );
};

export default ZentexTaskManager;
