import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Box,
  Breadcrumbs,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Grid,
  Link,
  Stack,
  Tab,
  Tabs,
  Typography,
  Alert,
  Tooltip,
  IconButton,
} from "@mui/material";
import {
  ArrowBack as ArrowBackIcon,
  HelpOutline as HelpIcon,
  History as HistoryIcon,
  PlayArrow as OngoingIcon,
  ErrorOutline as FailedIcon,
  PauseCircleOutline as PendingIcon,
  Close as CloseIcon,
  DeleteOutline as DeleteOutlineIcon,
} from "@mui/icons-material";
import { DataGrid, GridColDef } from "@mui/x-data-grid";

interface McpToolItem {
  tool_name: string;
  description: string;
  mapped_domain: string;
  plugin_id: string;
  feature_code: string;
  execution_domain?: string | null;
  read_only: boolean;
  side_effect_free: boolean;
  mutates_state: boolean;
  requires_cloud_audit: boolean;
  status: string;
}

interface McpServerDetailData {
  server_id: string;
  transport_type: string;
  status: string;
  tool_count: number;
  credit_score: number;
  total_tasks_run: number;
  success_rate: number;
  uptime_seconds: number;
  tools: McpToolItem[];
  error_message?: string | null;
}

interface McpTaskSummary {
  record_id: string;
  task_id?: string | null;
  action_type: string;
  status: string;
  start_time: string;
  end_time?: string | null;
  duration_seconds?: number | null;
  verification_status: string;
  error?: string | null;
}

const McpServerDetail: React.FC = () => {
  const { t } = useTranslation();
  const { server_id } = useParams<{ server_id: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<McpServerDetailData | null>(null);
  const [tasks, setTasks] = useState<McpTaskSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tabValue, setTabValue] = useState(0);
  const [creditInfoOpen, setCreditInfoOpen] = useState(false);
  const [deletingServer, setDeletingServer] = useState(false);

  useEffect(() => {
    if (server_id) {
      void loadDetail();
    }
  }, [server_id]);

  useEffect(() => {
    if (server_id) {
      void loadTasks();
    }
  }, [server_id, tabValue]);

  const loadDetail = async () => {
    setLoading(true);
    try {
      const response = await fetch(`/api/web/mcp-servers/${server_id}`);
      if (!response.ok) throw new Error(t("mcp.fetchDetailFailed"));
      const result = await response.json();
      setData(result);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadTasks = async () => {
    setTasksLoading(true);
    try {
      let statusQuery = "";
      if (tabValue === 0) statusQuery = "?status=running";
      else if (tabValue === 1) statusQuery = "?status=pending";
      else if (tabValue === 2) statusQuery = "?status=failed";
      // tabValue === 3 (历史记录) 不传status参数，返回所有任务

      const response = await fetch(`/api/web/mcp-servers/${server_id}/tasks${statusQuery}`);
      if (!response.ok) throw new Error(t("mcp.fetchTasksFailed"));
      const result = await response.json();
      setTasks(result);
    } catch (err: any) {
      console.error(err);
    } finally {
      setTasksLoading(false);
    }
  };

  const deleteServerRegistration = async () => {
    if (!data || !server_id) return;
    if (!window.confirm(t("mcp.deleteConfirm", { name: data.server_id }))) {
      return;
    }

    setDeletingServer(true);
    setError(null);
    try {
      const response = await fetch(`/api/web/mcp-servers/${encodeURIComponent(server_id)}`, {
        method: "DELETE",
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = payload?.detail;
        const message =
          typeof detail === "string" ? detail : detail?.operator_message || detail?.message || t("mcp.deleteFailed");
        throw new Error(message);
      }
      navigate("/console/mcp-servers");
    } catch (err: any) {
      setError(err?.message || t("mcp.deleteFailed"));
    } finally {
      setDeletingServer(false);
    }
  };

  const taskColumns: GridColDef[] = [
    { field: "record_id", headerName: t("mcp.recordId"), width: 120 },
    { field: "action_type", headerName: t("mcp.actionType"), flex: 1 },
    { field: "status", headerName: t("common.status"), width: 130, renderCell: (params) => (
      <Chip label={params.value} size="small" color={params.value === "completed" ? "success" : params.value === "failed" ? "error" : "primary"} />
    )},
    { field: "verification_status", headerName: t("mcp.verificationResult"), width: 130, renderCell: (params) => (
      <Chip label={params.value} size="small" variant="outlined" color={params.value === "passed" ? "success" : "warning"} />
    )},
    { field: "start_time", headerName: t("mcp.startTime"), width: 180 },
    { field: "duration_seconds", headerName: t("mcp.durationSeconds"), width: 100, valueGetter: (_value, row) => row.duration_seconds?.toFixed(2) || "-" },
    { field: "error", headerName: t("common.errorMessage"), width: 200, renderCell: (params) => (
      params.value ? (
        <Tooltip title={params.value}>
          <Typography variant="body2" noWrap sx={{ maxWidth: 180 }}>
            {params.value}
          </Typography>
        </Tooltip>
      ) : null
    )},
  ];

  if (loading) return (
    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '80vh' }}>
      <CircularProgress />
    </Box>
  );

  if (error || !data) return (
    <Box sx={{ p: 3 }}>
      <Alert severity="error">{error || t("mcp.serverNotFound")}</Alert>
      <Button startIcon={<ArrowBackIcon />} onClick={() => navigate("/console/mcp-servers")} sx={{ mt: 2 }}>
        {t("common.backToList")}
      </Button>
    </Box>
  );

  return (
    <Box sx={{ p: 4, maxWidth: 1400, margin: '0 auto' }}>
      <Stack spacing={4}>
        {/* Breadcrumbs & Navigation */}
        <Breadcrumbs aria-label="breadcrumb">
          <Link underline="hover" color="inherit" onClick={() => navigate("/console/mcp-servers")} sx={{ cursor: 'pointer' }}>
            {t("mcp.mcpManagement")}
          </Link>
          <Typography color="text.primary">{data.server_id}</Typography>
        </Breadcrumbs>

        <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
          <Box>
            <Typography variant="h3" fontWeight="bold">
              {data.server_id}
            </Typography>
            <Stack direction="row" spacing={2} sx={{ mt: 1 }}>
              <Chip label={data.status} color={data.status === "online" ? "success" : "warning"} />
              <Chip label={data.transport_type} variant="outlined" />
              <Typography variant="body2" color="text.secondary" sx={{ alignSelf: 'center' }}>
                {t("mcp.totalTools")}: {data.tool_count}
              </Typography>
            </Stack>
          </Box>
          <Stack direction="row" spacing={1}>
            <Button variant="outlined" startIcon={<ArrowBackIcon />} onClick={() => navigate("/console/mcp-servers")}>
              {t("mcp.backToDashboard")}
            </Button>
            <Button
              color="error"
              disabled={deletingServer}
              startIcon={<DeleteOutlineIcon />}
              onClick={() => void deleteServerRegistration()}
              variant="outlined"
            >
              {t("mcp.deleteServer")}
            </Button>
          </Stack>
        </Stack>

        <Grid container spacing={3}>
          {/* Credit Score & Summary Card */}
          <Grid size={{ xs: 12, md: 4 }}>
            <Card sx={{ height: '100%', borderRadius: 4, background: 'linear-gradient(135deg, #1e3c72 0%, #2a5298 100%)', color: 'white' }}>
              <CardContent>
                <Stack spacing={2} alignItems="center" sx={{ py: 2 }}>
                  <Typography variant="h6">{t("mcp.serverCreditScore")}</Typography>
                  <Box sx={{ position: 'relative', display: 'inline-flex' }}>
                    <CircularProgress
                      variant="determinate"
                      value={data.credit_score}
                      size={140}
                      thickness={5}
                      sx={{ color: 'rgba(255,255,255,0.2)' }}
                    />
                    <CircularProgress
                      variant="determinate"
                      value={data.credit_score}
                      size={140}
                      thickness={5}
                      sx={{
                        color: data.credit_score > 90 ? '#4caf50' : data.credit_score > 70 ? '#ff9800' : '#f44336',
                        position: 'absolute',
                        left: 0,
                      }}
                    />
                    <Box sx={{ position: 'absolute', top: 0, left: 0, bottom: 0, right: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <Typography variant="h3" fontWeight="bold">
                        {data.credit_score}
                      </Typography>
                    </Box>
                  </Box>
                  <Stack 
                    direction="row" 
                    spacing={1} 
                    alignItems="center" 
                    sx={{ cursor: 'pointer' }}
                    onClick={() => setCreditInfoOpen(true)}
                  >
                    <Typography variant="body2">{t("mcp.creditScoreExplanation")}</Typography>
                    <IconButton size="small" sx={{ color: 'white' }}>
                      <HelpIcon fontSize="small" />
                    </IconButton>
                  </Stack>
                </Stack>
                <Divider sx={{ borderColor: 'rgba(255,255,255,0.1)', my: 2 }} />
                <Stack spacing={1.5}>
                  <Stack direction="row" justifyContent="space-between">
                    <Typography variant="body2">{t("mcp.taskSuccessRate")}</Typography>
                    <Typography variant="body2" fontWeight="bold">{(data.success_rate * 100).toFixed(1)}%</Typography>
                  </Stack>
                  <Stack direction="row" justifyContent="space-between">
                    <Typography variant="body2">{t("mcp.cumulativeTasks")}</Typography>
                    <Typography variant="body2" fontWeight="bold">{data.total_tasks_run}</Typography>
                  </Stack>
                  <Stack direction="row" justifyContent="space-between">
                    <Typography variant="body2">{t("mcp.continuousUptime")}</Typography>
                    <Typography variant="body2" fontWeight="bold">{Math.floor(data.uptime_seconds / 3600)}h</Typography>
                  </Stack>
                </Stack>
              </CardContent>
            </Card>
          </Grid>

          {/* Quick Details Card */}
          <Grid size={{ xs: 12, md: 8 }}>
            <Card sx={{ height: '100%', borderRadius: 4 }}>
              <CardContent>
                <Typography variant="h6" gutterBottom>{t("mcp.serverMetadata")}</Typography>
                <Grid container spacing={2} sx={{ mb: 2 }}>
                  <Grid size={{ xs: 6 }}>
                    <Typography variant="caption" color="text.secondary">Server ID</Typography>
                    <Typography variant="body1" fontWeight="medium">{data.server_id}</Typography>
                  </Grid>
                  <Grid size={{ xs: 6 }}>
                    <Typography variant="caption" color="text.secondary">{t("mcp.accessProtocol")}</Typography>
                    <Typography variant="body1" fontWeight="medium">{data.transport_type}</Typography>
                  </Grid>
                </Grid>
                <Divider sx={{ my: 2 }} />
                <Typography variant="h6" gutterBottom>{t("mcp.toolDetailedList")} ({data.tools.length})</Typography>
                <Box sx={{ maxHeight: 300, overflow: 'auto' }}>
                  {data.tools.map(tool => (
                    <Box key={tool.plugin_id} sx={{ p: 2, mb: 1, border: '1px solid', borderColor: 'divider', borderRadius: 2 }}>
                      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                        <Typography variant="subtitle2" fontWeight="bold">{tool.tool_name}</Typography>
                        <Chip label={tool.mapped_domain} size="small" color={tool.mapped_domain === "cognitive" ? "primary" : "secondary"} />
                      </Stack>
                      <Typography variant="body2" color="text.secondary">{tool.description}</Typography>
                    </Box>
                  ))}
                </Box>
              </CardContent>
            </Card>
          </Grid>

          {/* Task Monitoring Section */}
          <Grid size={{ xs: 12 }}>
            <Card sx={{ borderRadius: 4 }}>
              <CardContent>
                <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
                  <Typography variant="h5">{t("mcp.realtimeTaskMonitoring")}</Typography>
                </Stack>
                <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}>
                  <Tabs value={tabValue} onChange={(_, v) => setTabValue(v)}>
                    <Tab icon={<OngoingIcon />} iconPosition="start" label={t("mcp.inProgress")} />
                    <Tab icon={<PendingIcon />} iconPosition="start" label={t("mcp.pendingAudit")} />
                    <Tab icon={<FailedIcon />} iconPosition="start" label={t("mcp.executionFailed")} />
                    <Tab icon={<HistoryIcon />} iconPosition="start" label={t("mcp.taskHistory")} />
                  </Tabs>
                </Box>
                <Box sx={{ height: 500 }}>
                  <DataGrid
                    rows={tasks}
                    columns={taskColumns}
                    loading={tasksLoading}
                    getRowId={(row) => row.record_id}
                    pageSizeOptions={[10, 25]}
                    initialState={{ pagination: { paginationModel: { pageSize: 10 } } }}
                    disableRowSelectionOnClick
                    sx={{ border: 'none' }}
                  />
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </Stack>

      {/* 信用分说明 Dialog */}
      <Dialog
        open={creditInfoOpen}
        onClose={() => setCreditInfoOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography variant="h6" fontWeight="bold">{t("mcp.creditScoreRules")}</Typography>
          <IconButton onClick={() => setCreditInfoOpen(false)} size="small">
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent dividers>
          <Stack spacing={3}>
            {/* 评分公式 */}
            <Box>
              <Typography variant="subtitle1" fontWeight="bold" gutterBottom>
                📊 {t("mcp.scoringFormula")}
              </Typography>
              <Box sx={{ 
                p: 2, 
                bgcolor: 'action.hover', 
                borderRadius: 1,
                fontFamily: 'monospace',
                fontSize: '1.1rem'
              }}>
                {t("mcp.creditScoreFormula")}
              </Box>
            </Box>

            {/* 等级划分 */}
            <Box>
              <Typography variant="subtitle1" fontWeight="bold" gutterBottom>
                🎯 {t("mcp.levelDivision")}
              </Typography>
              <Stack spacing={1}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Chip label={t("mcp.excellent")} size="small" sx={{ bgcolor: '#4caf50', color: 'white' }} />
                  <Typography>90-100{t("mcp.scoreUnit")}：{t("mcp.excellentDesc")}</Typography>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Chip label={t("mcp.good")} size="small" sx={{ bgcolor: '#ff9800', color: 'white' }} />
                  <Typography>70-89{t("mcp.scoreUnit")}：{t("mcp.goodDesc")}</Typography>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Chip label={t("mcp.warning")} size="small" sx={{ bgcolor: '#f44336', color: 'white' }} />
                  <Typography>&lt;70{t("mcp.scoreUnit")}：{t("mcp.warningDesc")}</Typography>
                </Box>
              </Stack>
            </Box>

            {/* 影响因素 */}
            <Box>
              <Typography variant="subtitle1" fontWeight="bold" gutterBottom>
                ⚙️ {t("mcp.influencingFactors")}
              </Typography>
              <Stack spacing={0.5}>
                <Typography variant="body2">• {t("mcp.factorFailureCount")}</Typography>
                <Typography variant="body2">• {t("mcp.factorTimeoutRate")}</Typography>
                <Typography variant="body2">• {t("mcp.factorHumanIntervention")}</Typography>
              </Stack>
            </Box>

            {/* 重置机制 */}
            <Box>
              <Typography variant="subtitle1" fontWeight="bold" gutterBottom>
                🔄 {t("mcp.resetMechanism")}
              </Typography>
              <Stack spacing={0.5}>
                <Typography variant="body2">• {t("mcp.resetDaily")}</Typography>
                <Typography variant="body2">• {t("mcp.resetRecovery")}</Typography>
              </Stack>
            </Box>

            {/* 当前服务器统计 */}
            {data && (
              <Box>
                <Typography variant="subtitle1" fontWeight="bold" gutterBottom>
                  📈 {t("mcp.currentServerStats")}
                </Typography>
                <Stack spacing={1}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2" color="text.secondary">{t("mcp.cumulativeTasks")}</Typography>
                    <Typography variant="body2" fontWeight="bold">{data.total_tasks_run}</Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2" color="text.secondary">{t("mcp.taskSuccessRate")}</Typography>
                    <Typography variant="body2" fontWeight="bold">{(data.success_rate * 100).toFixed(1)}%</Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2" color="text.secondary">{t("mcp.currentCreditScore")}</Typography>
                    <Typography variant="body2" fontWeight="bold" color={
                      data.credit_score > 90 ? 'success.main' : 
                      data.credit_score > 70 ? 'warning.main' : 
                      'error.main'
                    }>
                      {data.credit_score}
                    </Typography>
                  </Box>
                </Stack>
              </Box>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreditInfoOpen(false)} variant="contained">
            {t("common.gotIt")}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default McpServerDetail;
