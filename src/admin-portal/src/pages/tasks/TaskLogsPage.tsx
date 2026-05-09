import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { DataGrid, GridColDef } from '@mui/x-data-grid';
import {
  ArrowBack as BackIcon,
  Article as LogsIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';

interface TaskLogEntry {
  id: number;
  task_id: string;
  action: string;
  action_label?: string;
  operator_id: string;
  operator_label?: string;
  old_status: string | null;
  new_status: string | null;
  status_transition?: {
    from: string | null;
    from_label: string | null;
    to: string | null;
    to_label: string | null;
    changed: boolean;
  } | null;
  details: unknown;
  details_text?: string;
  summary?: string;
  trace_id: string | null;
  timestamp: string;
}

interface TaskLogsResponse {
  task_id: string | null;
  items: TaskLogEntry[];
  total: number;
  limit: number;
  offset: number;
}

const formatLogDetails = (value: unknown): string => {
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  if (typeof value === 'string') {
    return value;
  }
  return JSON.stringify(value);
};

const formatLogTime = (value: string | null | undefined): string => {
  if (!value) {
    return '-';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
};

const TaskLogsPage: React.FC = () => {
  const { t } = useTranslation();
  const { task_id } = useParams<{ task_id?: string }>();
  const navigate = useNavigate();
  const [rows, setRows] = useState<TaskLogEntry[]>([]);
  const [rowCount, setRowCount] = useState(0);
  const [paginationModel, setPaginationModel] = useState({ page: 0, pageSize: 25 });
  const [search, setSearch] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [status, setStatus] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isTaskScoped = Boolean(task_id);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set('limit', String(paginationModel.pageSize));
      params.set('offset', String(paginationModel.page * paginationModel.pageSize));
      if (appliedSearch.trim()) {
        params.set('search', appliedSearch.trim());
      }
      if (status !== 'all') {
        params.set('status', status);
      }
      const endpoint = task_id
        ? `/api/web/tasks/${encodeURIComponent(task_id)}/logs`
        : '/api/web/tasks/logs';
      const response = await fetch(`${endpoint}?${params.toString()}`);
      if (!response.ok) {
        throw new Error(`${t('tasks.logs.fetchFailed')}（HTTP ${response.status}）`);
      }
      const payload: TaskLogsResponse = await response.json();
      setRows(payload.items);
      setRowCount(payload.total);
    } catch (err) {
      console.error('Failed to fetch task logs', err);
      setError(err instanceof Error ? err.message : t('tasks.logs.fetchFailed'));
    } finally {
      setLoading(false);
    }
  }, [appliedSearch, paginationModel.page, paginationModel.pageSize, status, task_id, t]);

  useEffect(() => {
    void fetchLogs();
  }, [fetchLogs]);

  const columns: GridColDef[] = useMemo(() => [
    {
      field: 'timestamp',
      headerName: t('tasks.logs.time'),
      width: 190,
      valueGetter: (_value, row: TaskLogEntry) => formatLogTime(row.timestamp),
    },
    {
      field: 'task_id',
      headerName: t('tasks.taskId'),
      width: 130,
      hideable: isTaskScoped,
    },
    {
      field: 'summary',
      headerName: t('tasks.logs.summary'),
      minWidth: 360,
      flex: 1,
      valueGetter: (_value, row: TaskLogEntry) => row.summary || row.action_label || row.action,
      renderCell: (params) => (
        <Tooltip title={String(params.value || '-')} placement="top-start">
          <Typography variant="body2" sx={{ overflow: 'hidden', textOverflow: 'ellipsis', fontWeight: 500 }}>
            {String(params.value || '-')}
          </Typography>
        </Tooltip>
      ),
    },
    {
      field: 'action_label',
      headerName: t('tasks.logs.action'),
      width: 180,
      valueGetter: (_value, row: TaskLogEntry) => row.action_label || row.action,
    },
    {
      field: 'operator_id',
      headerName: t('tasks.logs.operator'),
      width: 150,
      valueGetter: (_value, row: TaskLogEntry) => row.operator_label || row.operator_id || '-',
    },
    {
      field: 'status_transition',
      headerName: t('tasks.logs.statusTransition'),
      width: 220,
      valueGetter: (_value, row: TaskLogEntry) => {
        const transition = row.status_transition;
        if (!transition) {
          return '-';
        }
        return `${transition.from_label || transition.from || '-'} -> ${transition.to_label || transition.to || '-'}`;
      },
    },
    {
      field: 'trace_id',
      headerName: t('tasks.logs.traceId'),
      width: 170,
      valueGetter: (_value, row: TaskLogEntry) => row.trace_id || '-',
    },
    {
      field: 'details_text',
      headerName: t('tasks.logs.details'),
      minWidth: 320,
      flex: 0.8,
      valueGetter: (_value, row: TaskLogEntry) => row.details_text || formatLogDetails(row.details),
      renderCell: (params) => (
        <Tooltip title={String(params.value || '-')} placement="top-start">
          <Typography variant="body2" sx={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {String(params.value || '-')}
          </Typography>
        </Tooltip>
      ),
    },
  ], [isTaskScoped, t]);

  const handleBack = () => {
    if (task_id) {
      navigate(`/console/tasks/${task_id}`);
      return;
    }
    navigate('/console/tasks');
  };

  const applySearch = () => {
    setPaginationModel((current) => ({ ...current, page: 0 }));
    setAppliedSearch(search);
  };

  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={3}>
        <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={2}>
          <Stack direction="row" spacing={2} alignItems="center">
            <IconButton onClick={handleBack} aria-label={t('tasks.logs.back')}>
              <BackIcon />
            </IconButton>
            <Box>
              <Typography variant="h4" component="h1" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <LogsIcon color="primary" />
                {isTaskScoped ? t('tasks.logs.taskTitle') : t('tasks.logs.moduleTitle')}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ wordBreak: 'break-word' }}>
                {isTaskScoped ? t('tasks.logs.taskSubtitle', { taskId: task_id }) : t('tasks.logs.moduleSubtitle')}
              </Typography>
            </Box>
          </Stack>
          <Stack direction="row" spacing={1}>
            <Button
              startIcon={<RefreshIcon />}
              onClick={() => void fetchLogs()}
              variant="outlined"
              disabled={loading}
            >
              {loading ? t('common.refreshing') : t('common.refresh')}
            </Button>
          </Stack>
        </Stack>

        {error ? (
          <Alert severity="error" data-testid="task-log-error">
            {error}
          </Alert>
        ) : null}

        <Card variant="outlined">
          <CardContent>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <TextField
                label={t('tasks.logs.search')}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') applySearch();
                }}
                fullWidth
                size="small"
              />
              <FormControl size="small" sx={{ minWidth: 180 }}>
                <InputLabel id="task-log-status-label">{t('tasks.logs.status')}</InputLabel>
                <Select
                  labelId="task-log-status-label"
                  label={t('tasks.logs.status')}
                  value={status}
                  onChange={(event) => {
                    setStatus(String(event.target.value));
                    setPaginationModel((current) => ({ ...current, page: 0 }));
                  }}
                >
                  <MenuItem value="all">{t('common.all', { defaultValue: '全部' })}</MenuItem>
                  <MenuItem value="todo">todo</MenuItem>
                  <MenuItem value="in_progress">in_progress</MenuItem>
                  <MenuItem value="blocked">blocked</MenuItem>
                  <MenuItem value="done">done</MenuItem>
                  <MenuItem value="failed">failed</MenuItem>
                  <MenuItem value="TASK_CREATED">TASK_CREATED</MenuItem>
                  <MenuItem value="TASK_STATUS_UPDATED">TASK_STATUS_UPDATED</MenuItem>
                </Select>
              </FormControl>
              <Button variant="contained" onClick={applySearch}>
                {t('common.search', { defaultValue: '搜索' })}
              </Button>
            </Stack>
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <Box sx={{ height: 640, width: '100%' }}>
              <DataGrid
                rows={rows}
                columns={columns}
                getRowId={(row) => row.id}
                loading={loading}
                pageSizeOptions={[10, 25, 50, 100]}
                paginationMode="server"
                paginationModel={paginationModel}
                onPaginationModelChange={setPaginationModel}
                rowCount={rowCount}
                disableRowSelectionOnClick
                localeText={{
                  noRowsLabel: t('tasks.logs.noData'),
                  toolbarDensity: t('tasks.density'),
                  toolbarFilters: t('tasks.filters'),
                  toolbarColumns: t('tasks.columns'),
                }}
              />
            </Box>
          </CardContent>
        </Card>
      </Stack>
    </Box>
  );
};

export default TaskLogsPage;
