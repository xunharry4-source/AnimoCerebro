import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Chip,
  Button,
  IconButton,
  Tooltip,
  LinearProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Alert,
  List,
  ListItem,
  ListItemText,
} from '@mui/material';
import { DataGrid, GridColDef } from '@mui/x-data-grid';
import {
  Assignment as TaskIcon,
  PlayArrow as ResumeIcon,
  Pause as PauseIcon,
  CheckCircle as ApproveIcon,
  Cancel as RejectIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';

// --- Types ---

export type TaskStatus = 'todo' | 'in_progress' | 'blocked' | 'waiting_confirmation' | 'done' | 'failed';

export interface ZentexTask {
  id: string; // Required for DataGrid
  task_id: string;
  subtask_id: string;
  idempotency_key: string;
  title: string;
  task_type: string;
  status: TaskStatus;
  progress: number;
  originator_id: string;
  remarks: string | null;
  started_at: string | null;
  completed_at: string | null;
}

// --- Components ---

const StatusChip = ({ status }: { status: TaskStatus }) => {
  const colorMap: Record<TaskStatus, any> = {
    todo: 'default',
    in_progress: 'primary',
    blocked: 'warning',
    waiting_confirmation: 'secondary',
    done: 'success',
    failed: 'error',
  };
  return (
    <Chip
      size="small"
      label={status.toUpperCase()}
      color={colorMap[status]}
      variant="outlined"
      sx={{ fontWeight: 'bold' }}
    />
  );
};

export const ZentexTaskManager: React.FC = () => {
  const [tasks, setTasks] = useState<ZentexTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [interveneDialog, setInterveneDialog] = useState<{ open: boolean; task: ZentexTask | null; action: string }>({ open: false, task: null, action: '' });
  const [idempotencyKey, setIdempotencyKey] = useState("");
  const [remarks, setRemarks] = useState('');

  const generateIdempotencyKey = () => {
    const uuid =
      (globalThis.crypto as any)?.randomUUID?.() ??
      `manual-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    return String(uuid);
  };

  const fetchTasks = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/web/tasks");
      if (!res.ok) {
        throw new Error(`获取任务列表失败（HTTP ${res.status}）`);
      }
      const data = await res.json();
      setTasks(data.map((t: any) => ({ ...t, id: t.task_id })));
    } catch (err) {
      console.error('Failed to fetch tasks', err);
      setError(err instanceof Error ? err.message : "获取任务列表失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks();
    const interval = setInterval(fetchTasks, 5000); // Poll every 5s
    return () => clearInterval(interval);
  }, []);

  const handleIntervene = async () => {
    if (!interveneDialog.task) return;
    try {
      const res = await fetch(`/api/web/tasks/${interveneDialog.task.task_id}/intervene`, {
        method: 'POST',
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: interveneDialog.action,
          idempotency_key: idempotencyKey,
          remarks,
          operator_id: "zentex-pro-mode",
        }),
      });
      if (res.ok) {
        fetchTasks();
        setInterveneDialog({ open: false, task: null, action: '' });
        setRemarks('');
        setIdempotencyKey("");
      } else {
          const err = await res.json();
          alert(`Intervention failed: ${err.detail}`);
      }
    } catch (err) {
      console.error('Intervention error', err);
    }
  };

  const columns: GridColDef[] = [
    { field: 'task_id', headerName: '任务ID', width: 100 },
    { field: 'subtask_id', headerName: '子ID', width: 100 },
    { field: 'title', headerName: '任务标题', width: 200 },
    { field: 'task_type', headerName: '任务类型', width: 130 },
    {
      field: 'status',
      headerName: '状态',
      width: 150,
      renderCell: (params) => <StatusChip status={params.value as TaskStatus} />,
    },
    {
      field: 'progress',
      headerName: '进度',
      width: 180,
      renderCell: (params) => (
        <Box sx={{ width: '100%', mt: 2 }}>
          <LinearProgress variant="determinate" value={params.value * 100} sx={{ height: 6, borderRadius: 3 }} />
          <Typography variant="caption" sx={{ color: '#718096' }}>{Math.round(params.value * 100)}%</Typography>
        </Box>
      ),
    },
    { field: 'originator_id', headerName: '发起方', width: 130 },
    { field: 'remarks', headerName: '最后备注', width: 220 },
    {
      field: 'actions',
      headerName: '人工干预',
      width: 200,
      sortable: false,
      renderCell: (params) => {
        const t = params.row as ZentexTask;
        return (
          <Box>
            {t.status === 'in_progress' && (
              <Tooltip title="暂停任务">
                <IconButton
                  onClick={() => {
                    setIdempotencyKey(generateIdempotencyKey());
                    setInterveneDialog({ open: true, task: t, action: "pause" });
                  }}
                  aria-label="pause-task"
                  color="warning"
                >
                  <PauseIcon />
                </IconButton>
              </Tooltip>
            )}
            {(t.status === 'blocked' || t.status === 'todo' || t.status === 'waiting_confirmation') && (
               <Tooltip title="恢复任务">
                  <IconButton
                    onClick={() => {
                      setIdempotencyKey(generateIdempotencyKey());
                      setInterveneDialog({ open: true, task: t, action: "resume" });
                    }}
                    aria-label="resume-task"
                    color="primary"
                  >
                    <ResumeIcon />
                  </IconButton>
               </Tooltip>
            )}
            {t.status === 'waiting_confirmation' && (
                <Tooltip title="批准">
                    <IconButton
                      onClick={() => {
                        setIdempotencyKey(generateIdempotencyKey());
                        setInterveneDialog({ open: true, task: t, action: "approve" });
                      }}
                      aria-label="approve-task"
                      color="success"
                    >
                        <ApproveIcon />
                    </IconButton>
                </Tooltip>
            )}
            {t.status !== 'done' && t.status !== 'failed' && (
                <Tooltip title="终止并拒绝">
                    <IconButton
                      onClick={() => {
                        setIdempotencyKey(generateIdempotencyKey());
                        setInterveneDialog({ open: true, task: t, action: "reject" });
                      }}
                      aria-label="reject-task"
                      color="error"
                    >
                        <RejectIcon />
                    </IconButton>
                </Tooltip>
            )}
          </Box>
        );
      },
    },
    { field: 'started_at', headerName: '开始时间', width: 180 },
  ];

  return (
    <Box sx={{ p: 4, bgcolor: '#0b0e14', minHeight: '100vh', color: '#fff' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 4, alignItems: 'center' }}>
        <Typography variant="h4" sx={{ fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: 2 }}>
          <TaskIcon color="primary" fontSize="large" />
          Zentex 独立任务管理中心
        </Typography>
        <Button startIcon={<RefreshIcon />} onClick={fetchTasks} sx={{ color: '#718096' }}>
          Refresh
        </Button>
      </Box>

      <Alert severity="info" sx={{ mb: 3, bgcolor: '#1a202c', color: '#fff', border: '1px solid #2d3748' }}>
        已实现物理隔离的任务状态机，所有状态变更均携带 <b>idempotency_key</b> 授信确认。
      </Alert>
      {error ? (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      ) : null}
      <List sx={{ mb: 2, bgcolor: '#111827', borderRadius: 2, border: '1px solid #2d3748' }}>
        {tasks.map((task) => (
          <ListItem key={`summary-${task.task_id}`} divider>
            <ListItemText
              primary={`${task.title} (${task.task_id})`}
              secondary={`${task.status} | ${task.idempotency_key} | ${task.remarks || "-"}`}
              primaryTypographyProps={{ color: '#fff' }}
              secondaryTypographyProps={{ color: '#a0aec0' }}
            />
          </ListItem>
        ))}
      </List>

      <Box sx={{ height: 600, width: '100%', bgcolor: '#1c222d', borderRadius: 2, overflow: 'hidden', border: '1px solid #2d3748' }}>
        <DataGrid
          rows={tasks}
          columns={columns}
          loading={loading}
          getRowId={(row) => row.task_id}
          disableVirtualization
          pageSizeOptions={[10, 25]}
          initialState={{ pagination: { paginationModel: { pageSize: 10 } } }}
          disableRowSelectionOnClick
          sx={{
            color: '#e2e8f0', borderColor: '#2d3748',
            '& .MuiDataGrid-cell': { borderColor: '#2d3748' },
            '& .MuiDataGrid-columnHeaders': { bgcolor: '#2d3748', color: '#fff', borderBottom: '1px solid #4a5568' },
            '& .MuiDataGrid-footerContainer': { bgcolor: '#1c222d', borderTop: '1px solid #2d3748' },
            '& .MuiCheckbox-root': { color: '#4a5568' },
          }}
        />
      </Box>

      {/* Intervention Dialog */}
      <Dialog open={interveneDialog.open} onClose={() => setInterveneDialog({ open: false, task: null, action: '' })}
        PaperProps={{ sx: { bgcolor: '#1a202c', color: '#fff', borderRadius: 4 } }}
      >
        <DialogTitle sx={{ fontWeight: 'bold', textTransform: 'capitalize' }}>
           确认干预: {interveneDialog.action}
        </DialogTitle>
        <DialogContent sx={{ mt: 1 }}>
          <Typography variant="body2" color="#718096" gutterBottom>
             任务 ID: {interveneDialog.task?.task_id} - {interveneDialog.task?.title}
          </Typography>
          <TextField
              label="idempotency_key（必填）"
              fullWidth
              variant="outlined"
              value={idempotencyKey}
              onChange={(e) => setIdempotencyKey(e.target.value)}
              sx={{ mt: 2, '& .MuiOutlinedInput-root': { '& fieldset': { borderColor: '#2d3748' } } }}
              InputLabelProps={{ style: { color: '#718096' } }}
              inputProps={{ style: { color: '#fff', fontFamily: "monospace" } }}
          />
          <TextField
              label="干预备注 (Mandatory for Audit)"
              fullWidth
              multiline
              rows={3}
              variant="outlined"
              value={remarks}
              onChange={(e) => setRemarks(e.target.value)}
              sx={{ mt: 2, '& .MuiOutlinedInput-root': { '& fieldset': { borderColor: '#2d3748' } } }}
              InputLabelProps={{ style: { color: '#718096' } }}
              inputProps={{ style: { color: '#fff' } }}
          />
        </DialogContent>
        <DialogActions sx={{ p: 3 }}>
          <Button onClick={() => setInterveneDialog({ open: false, task: null, action: '' })} sx={{ color: '#718096' }}>Cancel</Button>
          <Button
            onClick={handleIntervene}
            variant="contained"
            disabled={!idempotencyKey.trim()}
            color={interveneDialog.action === 'reject' ? 'error' : 'primary'}
          >
             Confirm Action
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ZentexTaskManager;
