import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  LinearProgress,
  Stack,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  Paper,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import StarIcon from "@mui/icons-material/Star";
import HistoryIcon from "@mui/icons-material/History";
import PendingIcon from "@mui/icons-material/Pending";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";

type CliToolDetail = {
  command_name: string;
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
  help_doc_url?: string | null;
  project_path?: string | null;
  project_name?: string | null;
  project_description?: string | null;
  credit_score: {
    total_score: number;
    success_rate: number;
    total_executions: number;
    successful_executions: number;
    failed_executions: number;
    average_response_time_ms?: number | null;
    error_rate: number;
    usage_frequency: string;
    credit_level: string;
    last_updated: string;
  };
  task_statistics: {
    in_progress: number;
    pending: number;
    failed: number;
    completed: number;
    total: number;
  };
};

type TaskItem = {
  task_id: string;
  title: string;
  status: string;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  progress: number;
  priority: string;
  remarks?: string | null;
};

type ExecutionHistoryItem = {
  trace_id: string;
  tool_name: string;
  status: string;
  exit_code: number;
  stdout: string;
  stderr: string;
  command_line: string[];
  working_directory?: string | null;
  executed_at: string;
  duration_ms?: number | null;
};

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;
  return (
    <div role="tabpanel" hidden={value !== index} id={`cli-tool-tabpanel-${index}`} aria-labelledby={`cli-tool-tab-${index}`} {...other}>
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

export default function CliToolDetailPage() {
  const { t } = useTranslation();
  const { toolName } = useParams<{ toolName: string }>();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<CliToolDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tabValue, setTabValue] = useState(0);
  const [tasks, setTasks] = useState<{ "in-progress": TaskItem[]; pending: TaskItem[]; failed: TaskItem[] }>({
    "in-progress": [],
    pending: [],
    failed: [],
  });
  const [history, setHistory] = useState<ExecutionHistoryItem[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);

  useEffect(() => {
    if (toolName) {
      void loadToolDetail(toolName);
    }
  }, [toolName]);

  useEffect(() => {
    if (detail && tabValue >= 0 && tabValue <= 2) {
      const statusFilters = ["in-progress", "pending", "failed"];
      void loadTasks(toolName!, statusFilters[tabValue]);
    } else if (detail && tabValue === 3) {
      void loadHistory(toolName!);
    }
  }, [tabValue, detail, toolName]);

  const loadToolDetail = async (name: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/web/cli-tools/${name}/detail`);
      if (!response.ok) {
        throw new Error(t("cli.fetchDetailFailed", { status: response.status }));
      }
      const data = await response.json();
      setDetail(data);
    } catch (err: any) {
      setError(err?.message || t("cli.fetchDetailFailedGeneric"));
    } finally {
      setLoading(false);
    }
  };

  const loadTasks = async (name: string, statusFilter: string) => {
    setTasksLoading(true);
    try {
      const response = await fetch(`/api/web/cli-tools/${name}/tasks/${statusFilter}`);
      if (!response.ok) {
        throw new Error(t("cli.fetchTasksFailed", { status: response.status }));
      }
      const data = await response.json();
      setTasks((prev) => ({ ...prev, [statusFilter]: data }));
    } catch (err: any) {
      console.error(t("cli.loadTasksError"), err);
    } finally {
      setTasksLoading(false);
    }
  };

  const loadHistory = async (name: string) => {
    setHistoryLoading(true);
    try {
      const response = await fetch(`/api/web/cli-tools/${name}/execution-history?limit=50`);
      if (!response.ok) {
        throw new Error(t("cli.fetchHistoryFailed", { status: response.status }));
      }
      const data = await response.json();
      setHistory(data);
    } catch (err: any) {
      console.error(t("cli.loadHistoryError"), err);
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const getCreditLevelColor = (level: string) => {
    switch (level) {
      case "excellent":
        return "success";
      case "good":
        return "primary";
      case "fair":
        return "warning";
      case "poor":
        return "error";
      default:
        return "default";
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "success":
        return "success";
      case "failed":
        return "error";
      case "in_progress":
        return "info";
      default:
        return "default";
    }
  };

  const formatDateTime = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleString("zh-CN");
    } catch {
      return dateStr;
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "400px" }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error || !detail) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error" sx={{ mb: 2 }}>
          {error || t("cli.toolNotFound")}
        </Alert>
        <Button startIcon={<ArrowBackIcon />} onClick={() => navigate("/console/cli-tools")}>
          {t("common.backToList")}
        </Button>
      </Box>
    );
  }

  const creditScore = detail.credit_score;
  const creditLevelColors: Record<string, string> = {
    excellent: "#4caf50",
    good: "#2196f3",
    fair: "#ff9800",
    poor: "#f44336",
  };

  return (
    <Box sx={{ p: 3 }}>
      <Button startIcon={<ArrowBackIcon />} onClick={() => navigate("/console/cli-tools")} sx={{ mb: 2 }}>
        {t("cli.backToCliList")}
      </Button>

      {/* 工具基本信息卡片 */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 2 }}>
            <Box>
              <Typography variant="h4" gutterBottom>
                {detail.command_name}
              </Typography>
              <Typography variant="body1" color="text.secondary">
                {detail.description}
              </Typography>
            </Box>
            <Chip label={detail.status} color={detail.status === "active" ? "success" : "warning"} size="medium" />
          </Stack>

          <Divider sx={{ my: 2 }} />

          <Stack spacing={2}>
            <Box>
              <Typography variant="subtitle2" color="text.secondary">
                {t("cli.mappedDomain")}
              </Typography>
              <Chip
                label={detail.mapped_domain === "cognitive" ? t("cli.domainCognitive") : t("cli.domainExecution")}
                color={detail.mapped_domain === "cognitive" ? "primary" : "error"}
                size="small"
                sx={{ mt: 0.5 }}
              />
            </Box>
            <Box>
              <Typography variant="subtitle2" color="text.secondary">
                {t("cli.pluginId")}
              </Typography>
              <Typography variant="body2" fontFamily="monospace">
                {detail.plugin_id}
              </Typography>
            </Box>
            <Box>
              <Typography variant="subtitle2" color="text.secondary">
                {t("cli.featureCode")}
              </Typography>
              <Typography variant="body2" fontFamily="monospace">
                {detail.feature_code}
              </Typography>
            </Box>
            <Box>
              <Typography variant="subtitle2" color="text.secondary">
                {t("cli.readOnlyMode")}
              </Typography>
              <Chip label={detail.read_only ? t("common.yes") : t("common.no")} color={detail.read_only ? "success" : "warning"} size="small" sx={{ mt: 0.5 }} />
            </Box>
            <Box>
              <Typography variant="subtitle2" color="text.secondary">
                {t("cli.requiresCloudAudit")}
              </Typography>
              <Chip
                label={detail.requires_cloud_audit ? t("common.yes") : t("common.no")}
                color={detail.requires_cloud_audit ? "warning" : "success"}
                size="small"
                sx={{ mt: 0.5 }}
              />
            </Box>
            {detail.project_name && (
              <Box>
                <Typography variant="subtitle2" color="text.secondary">
                  {t("cli.projectName")}
                </Typography>
                <Typography variant="body2">{detail.project_name}</Typography>
              </Box>
            )}
          </Stack>
        </CardContent>
      </Card>

      {/* 信用分卡片 */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
            <StarIcon sx={{ color: creditLevelColors[creditScore.credit_level] || "#999" }} />
            <Typography variant="h5">{t("cli.creditScore")}</Typography>
          </Stack>

          <Stack spacing={3}>
            <Box sx={{ textAlign: "center" }}>
              <Typography variant="h2" sx={{ color: creditLevelColors[creditScore.credit_level] || "#999", fontWeight: "bold" }}>
                {creditScore.total_score.toFixed(1)}
              </Typography>
              <Chip
                label={
                  creditScore.credit_level === "excellent"
                    ? t("cli.levelExcellent")
                    : creditScore.credit_level === "good"
                    ? t("cli.levelGood")
                    : creditScore.credit_level === "fair"
                    ? t("cli.levelFair")
                    : t("cli.levelPoor")
                }
                color={getCreditLevelColor(creditScore.credit_level) as any}
                sx={{ mt: 1 }}
              />
            </Box>

            <Stack spacing={2}>
              <Box>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  {t("cli.successRate")}
                </Typography>
                <LinearProgress
                  variant="determinate"
                  value={creditScore.success_rate * 100}
                  sx={{ height: 8, borderRadius: 1 }}
                  color={creditScore.success_rate > 0.8 ? "success" : creditScore.success_rate > 0.5 ? "warning" : "error"}
                />
                <Typography variant="caption" color="text.secondary">
                  {(creditScore.success_rate * 100).toFixed(1)}%
                </Typography>
              </Box>
              <Box>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  {t("cli.totalExecutions")}
                </Typography>
                <Typography variant="h6">{creditScore.total_executions}</Typography>
              </Box>
              <Stack direction="row" spacing={4}>
                <Box>
                  <Typography variant="body2" color="text.secondary">
                    {t("cli.successfulExecutions")}
                  </Typography>
                  <Typography variant="body1" color="success.main">
                    {creditScore.successful_executions}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="body2" color="text.secondary">
                    {t("cli.failedExecutions")}
                  </Typography>
                  <Typography variant="body1" color="error.main">
                    {creditScore.failed_executions}
                  </Typography>
                </Box>
              </Stack>
              <Box>
                <Typography variant="body2" color="text.secondary">
                  {t("cli.usageFrequency")}
                </Typography>
                <Chip
                  label={
                    creditScore.usage_frequency === "high" ? t("cli.freqHigh") : creditScore.usage_frequency === "medium" ? t("cli.freqMedium") : t("cli.freqLow")
                  }
                  size="small"
                  sx={{ mt: 0.5 }}
                />
              </Box>
            </Stack>
          </Stack>
        </CardContent>
      </Card>

      {/* 任务统计卡片 */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            {t("cli.taskStatistics")}
          </Typography>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <Box sx={{ flex: 1, textAlign: "center", p: 2, bgcolor: "info.lighter", borderRadius: 1 }}>
              <PendingIcon sx={{ fontSize: 40, color: "info.main" }} />
              <Typography variant="h4" color="info.main">
                {detail.task_statistics.in_progress}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t("tasks.status.in_progress")}
              </Typography>
            </Box>
            <Box sx={{ flex: 1, textAlign: "center", p: 2, bgcolor: "warning.lighter", borderRadius: 1 }}>
              <PendingIcon sx={{ fontSize: 40, color: "warning.main" }} />
              <Typography variant="h4" color="warning.main">
                {detail.task_statistics.pending}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t("tasks.status.pending")}
              </Typography>
            </Box>
            <Box sx={{ flex: 1, textAlign: "center", p: 2, bgcolor: "error.lighter", borderRadius: 1 }}>
              <ErrorIcon sx={{ fontSize: 40, color: "error.main" }} />
              <Typography variant="h4" color="error.main">
                {detail.task_statistics.failed}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t("tasks.status.failed")}
              </Typography>
            </Box>
            <Box sx={{ flex: 1, textAlign: "center", p: 2, bgcolor: "success.lighter", borderRadius: 1 }}>
              <CheckCircleIcon sx={{ fontSize: 40, color: "success.main" }} />
              <Typography variant="h4" color="success.main">
                {detail.task_statistics.completed}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t("tasks.status.completed")}
              </Typography>
            </Box>
          </Stack>
        </CardContent>
      </Card>

      {/* 任务标签页 */}
      <Card>
        <Tabs value={tabValue} onChange={handleTabChange} aria-label="CLI tool tabs">
          <Tab label={`${t("tasks.status.in_progress")} (${detail.task_statistics.in_progress})`} />
          <Tab label={`${t("tasks.status.pending")} (${detail.task_statistics.pending})`} />
          <Tab label={`${t("tasks.status.failed")} (${detail.task_statistics.failed})`} />
          <Tab icon={<HistoryIcon />} label={t("cli.executionHistory")} iconPosition="start" />
        </Tabs>

        <TabPanel value={tabValue} index={0}>
          {tasksLoading ? (
            <CircularProgress />
          ) : tasks["in-progress"].length > 0 ? (
            <TableContainer component={Paper}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t("cli.taskId")}</TableCell>
                    <TableCell>{t("cli.title")}</TableCell>
                    <TableCell>{t("cli.progress")}</TableCell>
                    <TableCell>{t("cli.startTime")}</TableCell>
                    <TableCell>{t("cli.priority")}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {tasks["in-progress"].map((task) => (
                    <TableRow key={task.task_id}>
                      <TableCell>{task.task_id}</TableCell>
                      <TableCell>{task.title}</TableCell>
                      <TableCell>
                        <LinearProgress variant="determinate" value={task.progress * 100} sx={{ width: 100 }} />
                        <Typography variant="caption">{(task.progress * 100).toFixed(0)}%</Typography>
                      </TableCell>
                      <TableCell>{task.started_at ? formatDateTime(task.started_at) : "-"}</TableCell>
                      <TableCell>
                        <Chip label={task.priority} size="small" />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          ) : (
            <Typography color="text.secondary">{t("cli.noInProgressTasks")}</Typography>
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={1}>
          {tasksLoading ? (
            <CircularProgress />
          ) : tasks.pending.length > 0 ? (
            <TableContainer component={Paper}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t("cli.taskId")}</TableCell>
                    <TableCell>{t("cli.title")}</TableCell>
                    <TableCell>{t("cli.createdAt")}</TableCell>
                    <TableCell>{t("cli.priority")}</TableCell>
                    <TableCell>{t("cli.remarks")}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {tasks.pending.map((task) => (
                    <TableRow key={task.task_id}>
                      <TableCell>{task.task_id}</TableCell>
                      <TableCell>{task.title}</TableCell>
                      <TableCell>{formatDateTime(task.created_at)}</TableCell>
                      <TableCell>
                        <Chip label={task.priority} size="small" />
                      </TableCell>
                      <TableCell>{task.remarks || "-"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          ) : (
            <Typography color="text.secondary">{t("cli.noPendingTasks")}</Typography>
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={2}>
          {tasksLoading ? (
            <CircularProgress />
          ) : tasks.failed.length > 0 ? (
            <TableContainer component={Paper}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t("cli.taskId")}</TableCell>
                    <TableCell>{t("cli.title")}</TableCell>
                    <TableCell>{t("cli.completedAt")}</TableCell>
                    <TableCell>{t("cli.remarks")}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {tasks.failed.map((task) => (
                    <TableRow key={task.task_id}>
                      <TableCell>{task.task_id}</TableCell>
                      <TableCell>{task.title}</TableCell>
                      <TableCell>{task.completed_at ? formatDateTime(task.completed_at) : "-"}</TableCell>
                      <TableCell>{task.remarks || "-"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          ) : (
            <Typography color="text.secondary">{t("cli.noFailedTasks")}</Typography>
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={3}>
          {historyLoading ? (
            <CircularProgress />
          ) : history.length > 0 ? (
            <TableContainer component={Paper}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t("cli.traceId")}</TableCell>
                    <TableCell>{t("common.status")}</TableCell>
                    <TableCell>{t("cli.exitCode")}</TableCell>
                    <TableCell>{t("cli.executedAt")}</TableCell>
                    <TableCell>{t("cli.durationMs")}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {history.map((entry) => (
                    <TableRow key={entry.trace_id}>
                      <TableCell sx={{ fontFamily: "monospace", fontSize: "0.75rem" }}>
                        {entry.trace_id.substring(0, 12)}...
                      </TableCell>
                      <TableCell>
                        <Chip label={entry.status} color={getStatusColor(entry.status) as any} size="small" />
                      </TableCell>
                      <TableCell>{entry.exit_code}</TableCell>
                      <TableCell>{formatDateTime(entry.executed_at)}</TableCell>
                      <TableCell>{entry.duration_ms ?? "-"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          ) : (
            <Typography color="text.secondary">{t("cli.noExecutionHistory")}</Typography>
          )}
        </TabPanel>
      </Card>
    </Box>
  );
}
