import React, { useState } from 'react';
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
  Assignment as TaskIcon,
  Refresh as RefreshIcon,
  PlayCircle as TestIcon,
} from '@mui/icons-material';
import { DataGrid, GridColDef } from '@mui/x-data-grid';

// Import modular components
import useTaskManagement from './useTaskManagement';
import StatusChip from './TaskStatusChip';
import TaskTabPanel from './TaskTabPanel';
import { ZentexTask } from './types';

const ZentexTaskManager: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const {
    tasksByStatus,
    loading,
    error,
    fetchTasks,
    loadTestTasks, // Add test data loader
    currentTasks,
    tabValue,
    setTabValue,
    sourceModuleFilter,
    setSourceModuleFilter,
  } = useTaskManagement();

  const TABS = [
    { label: t('tasks.inProgress'), key: 'in_progress' },
    { label: t('tasks.pending'), key: 'pending' },
    { label: t('tasks.waitingConfirmation'), key: 'waiting_confirmation' },
    { label: t('tasks.completed'), key: 'completed' },
    { label: t('tasks.cancelled'), key: 'cancelled' },
  ];

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const handleViewDetail = (task: ZentexTask) => {
    navigate(`/console/tasks/${task.task_id}`);
  };

  const columns: GridColDef[] = [
    { field: 'task_id', headerName: t('tasks.taskId'), width: 100 },
    { field: 'title', headerName: t('tasks.title'), width: 250 },
    { field: 'task_type', headerName: t('tasks.type'), width: 150 },
    {
      field: 'source_module',
      headerName: t('tasks.sourceModule'),
      width: 140,
      valueGetter: (params: any) => params.row.metadata?.source_module || 'core',
    },
    {
      field: 'workflow_status',
      headerName: t('tasks.workflowStatus'),
      width: 150,
      valueGetter: (params: any) => params.row.metadata?.workflow_status || '--',
    },
    {
      field: 'status',
      headerName: t('tasks.status'),
      width: 150,
      renderCell: (params) => <StatusChip status={params.value} />,
    },
    {
      field: 'priority',
      headerName: t('tasks.priority'),
      width: 100,
      valueGetter: (params: any) => params.row.priority || 'medium',
    },
    {
      field: 'progress',
      headerName: t('tasks.progress'),
      width: 150,
      renderCell: (params) => (
        <Box sx={{ width: '100%', display: 'flex', alignItems: 'center', gap: 1 }}>
          <Box
            sx={{
              flex: 1,
              height: 8,
              borderRadius: 4,
              bgcolor: 'action.hover',
              position: 'relative',
            }}
          >
            <Box
              sx={{
                position: 'absolute',
                left: 0,
                top: 0,
                height: '100%',
                width: `${params.value * 100}%`,
                borderRadius: 4,
                bgcolor: 'primary.main',
              }}
            />
          </Box>
          <Typography variant="caption" color="text.secondary">
            {Math.round(params.value * 100)}%
          </Typography>
        </Box>
      ),
    },
    { field: 'originator_id', headerName: t('tasks.originator'), width: 130 },
    {
      field: 'actions',
      headerName: t('tasks.actions'),
      width: 120,
      sortable: false,
      renderCell: (params) => (
        <Button
          size="small"
          variant="outlined"
          onClick={() => handleViewDetail(params.row)}
          startIcon={<TaskIcon />}
        >
          详情
        </Button>
      ),
    },
    { field: 'created_at', headerName: t('tasks.createdAt'), width: 180 },
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
              startIcon={<TestIcon />} 
              onClick={loadTestTasks} 
              variant="contained"
              color="secondary"
            >
              加载测试数据
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

        {/* Info Alert */}
        <Alert severity="info" sx={{ bgcolor: 'info.50', border: '1px solid', borderColor: 'info.200' }}>
          {t('tasks.tabInfo')}
        </Alert>

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
            <MenuItem value="reflection">{t('tasks.sourceModules.reflection')}</MenuItem>
            <MenuItem value="upgrade">{t('tasks.sourceModules.upgrade')}</MenuItem>
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
                const count = tasksByStatus[tab.key as keyof typeof tasksByStatus]?.length || 0;
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
                    rows={index === 0 ? tasksByStatus.in_progress :
                          index === 1 ? tasksByStatus.pending :
                          index === 2 ? tasksByStatus.waiting_confirmation :
                          index === 3 ? tasksByStatus.completed :
                          tasksByStatus.cancelled}
                    columns={columns}
                    loading={loading}
                    getRowId={(row) => row.task_id}
                    pageSizeOptions={[10, 25, 50]}
                    initialState={{ pagination: { paginationModel: { pageSize: 10 } } }}
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
