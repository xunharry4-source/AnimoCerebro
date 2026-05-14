import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useParams } from 'react-router-dom';
import {
  Alert,
  AlertTitle,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Stack,
  Typography,
} from '@mui/material';
import {
  ArrowBack as BackIcon,
  Article as LogsIcon,
} from '@mui/icons-material';
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { ZentexTask } from './types';
import StatusChip from './TaskStatusChip';
import {
  formatExecutionParty,
  formatTaskDateTime,
  formatTaskVerificationMethod,
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

interface TaskAuditLog {
  id: number | string;
  task_id: string;
  action: string;
  operator_id?: string | null;
  old_status?: string | null;
  new_status?: string | null;
  details?: any;
  trace_id?: string | null;
  timestamp?: string | null;
  explanation?: string;
}

interface TaskLogsResponse {
  items: TaskAuditLog[];
  total: number;
  limit: number;
  offset: number;
}

interface ReactGraphNodeRun {
  node_id?: string;
  attempt?: number;
  status?: string;
  started_at?: string;
  finished_at?: string;
  input?: Record<string, any>;
  output?: Record<string, any>;
  error?: Record<string, any> | null;
  evidence_refs?: unknown[];
}

type TaskWorkflowNodeData = {
  title: string;
  category: string;
  taskId?: string;
  status: string;
  executor: string;
  startedAt: string;
  finishedAt: string;
  inputSummary: string;
  outputSummary: string;
  runtimeSummary: string;
  errorReason: string;
  inputPayload: Record<string, any>;
  outputPayload: Record<string, any>;
  runtimePayload: Record<string, any>;
  logs: TaskAuditLog[];
};

const EMPTY_VALUE = '-';
const ACTIVE_STATUSES = new Set(['assignment_pending', 'todo', 'in_progress', 'waiting_confirmation']);

const isRecord = (value: unknown): value is Record<string, any> => {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
};

const parseMaybeJson = (value: unknown): unknown => {
  if (typeof value !== 'string') {
    return value;
  }
  const trimmed = value.trim();
  if (!trimmed || (!trimmed.startsWith('{') && !trimmed.startsWith('['))) {
    return value;
  }
  try {
    return JSON.parse(trimmed);
  } catch {
    return value;
  }
};

const compactJson = (value: unknown): string => {
  if (value === null || value === undefined || value === '') {
    return EMPTY_VALUE;
  }
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return JSON.stringify(value, null, 2);
};

const shortText = (value: unknown, maxLength = 120): string => {
  const text = compactJson(value).replace(/\s+/g, ' ').trim();
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength - 1)}...`;
};

const firstReadableValue = (...values: unknown[]): string => {
  for (const value of values) {
    if (typeof value === 'string' && value.trim().length > 0) {
      return value.trim();
    }
    if (typeof value === 'number' || typeof value === 'boolean') {
      return String(value);
    }
    if (Array.isArray(value) && value.length > 0) {
      return value.map((item) => compactJson(item)).join('；');
    }
  }
  return EMPTY_VALUE;
};

const taskNodeId = (taskId: string) => `task-${taskId}`;
const reactNodeId = (taskId: string, index: number, run: ReactGraphNodeRun) =>
  `react-${taskId}-${index}-${String(run.node_id || 'node').replace(/[^A-Za-z0-9_-]/g, '-')}`;

const statusColor = (status: string): 'default' | 'success' | 'warning' | 'error' | 'info' => {
  if (['done', 'completed'].includes(status)) return 'success';
  if (['failed', 'blocked', 'cancelled'].includes(status)) return 'error';
  if (['todo', 'assignment_pending', 'in_progress', 'waiting_confirmation'].includes(status)) return 'warning';
  if (['suspended', 'archived'].includes(status)) return 'default';
  return 'info';
};

const statusBorder = (status: string): string => {
  if (['done', 'completed'].includes(status)) return 'rgba(46,125,50,0.58)';
  if (['failed', 'blocked', 'cancelled'].includes(status)) return 'rgba(211,47,47,0.62)';
  if (ACTIVE_STATUSES.has(status)) return 'rgba(237,108,2,0.58)';
  return 'rgba(15,23,42,0.2)';
};

const extractObjective = (task: ZentexTask): string => {
  const metadata = task.metadata || {};
  const contract = task.contract || {};
  const expectedOutcome = isRecord(contract.expected_outcome) ? contract.expected_outcome : {};
  const q9Blueprint = isRecord(metadata.q9_action_blueprint) ? metadata.q9_action_blueprint : {};
  const q8Task = isRecord(metadata.q9_q8_task) ? metadata.q9_q8_task : {};
  return firstReadableValue(
    metadata.objective,
    metadata.intent_objective,
    expectedOutcome.objective,
    q9Blueprint.plan_objective,
    q8Task.intent_objective,
    metadata.summary,
    task.remarks,
  );
};

const extractErrorReason = (task: ZentexTask): string => {
  const metadata = task.metadata || {};
  const dispatchFailure = isRecord(metadata.dispatch_failure) ? metadata.dispatch_failure : {};
  const timeoutRecovery = isRecord(metadata.timeout_recovery) ? metadata.timeout_recovery : {};
  return firstReadableValue(
    task.last_error,
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

const buildTaskNodeData = (
  task: ZentexTask,
  category: string,
  logs: TaskAuditLog[],
  t: ReturnType<typeof useTranslation>['t'],
): TaskWorkflowNodeData => {
  const metadata = task.metadata || {};
  const output = parseMaybeJson(task.execution_output);
  const inputPayload = {
    task_id: task.task_id,
    title: task.title,
    objective: extractObjective(task),
    verification_method: formatTaskVerificationMethod(task, t),
    task_type: task.task_type,
    task_scope: task.task_scope,
    originator_id: task.originator_id,
    target_id: task.target_id,
    parent_task_id: task.parent_task_id,
    depends_on: task.depends_on,
    remarks: task.remarks,
    contract: task.contract,
    metadata,
  };
  const outputPayload = {
    status: task.status,
    progress: task.progress,
    execution_output: output,
    last_error: task.last_error,
    verification_result: metadata.verification_result,
    dispatch_failure: metadata.dispatch_failure,
    timeout_recovery: metadata.timeout_recovery,
  };
  const runtimePayload = {
    task_id: task.task_id,
    executor: formatExecutionParty(task, t),
    execution_assignment: task.execution_assignment,
    execution_started_at: task.execution_started_at,
    execution_finished_at: task.execution_finished_at,
    started_at: task.started_at,
    completed_at: task.completed_at,
    attempt_count: task.attempt_count,
    audit_log_total: logs.length,
    audit_logs: logs,
  };
  const errorReason = extractErrorReason(task);

  return {
    title: task.title || task.task_id,
    category,
    taskId: task.task_id,
    status: task.status,
    executor: formatExecutionParty(task, t),
    startedAt: formatTaskDateTime(taskStartTime(task)),
    finishedAt: formatTaskDateTime(taskEndTime(task)),
    inputSummary: shortText(inputPayload.objective || task.remarks || inputPayload.contract),
    outputSummary: shortText(output || task.last_error || metadata.verification_result || task.status),
    runtimeSummary: `${formatExecutionParty(task, t)} | ${formatTaskDateTime(taskStartTime(task))} -> ${formatTaskDateTime(taskEndTime(task))}`,
    errorReason,
    inputPayload,
    outputPayload,
    runtimePayload,
    logs,
  };
};

const buildBoundaryNodeData = (
  category: string,
  title: string,
  status: string,
  inputPayload: Record<string, any>,
  outputPayload: Record<string, any>,
): TaskWorkflowNodeData => ({
  title,
  category,
  status,
  executor: EMPTY_VALUE,
  startedAt: EMPTY_VALUE,
  finishedAt: EMPTY_VALUE,
  inputSummary: shortText(inputPayload),
  outputSummary: shortText(outputPayload),
  runtimeSummary: shortText({ status }),
  errorReason: EMPTY_VALUE,
  inputPayload,
  outputPayload,
  runtimePayload: { status },
  logs: [],
});

const extractReactGraphRuns = (task: ZentexTask): ReactGraphNodeRun[] => {
  const reactExecution = isRecord(task.metadata?.react_execution) ? task.metadata?.react_execution : {};
  const graphRuns = Array.isArray(reactExecution.graph_runs) ? reactExecution.graph_runs : [];
  return graphRuns.filter(isRecord).map((run) => ({
    node_id: typeof run.node_id === 'string' ? run.node_id : undefined,
    attempt: typeof run.attempt === 'number' ? run.attempt : undefined,
    status: typeof run.status === 'string' ? run.status : undefined,
    started_at: typeof run.started_at === 'string' ? run.started_at : undefined,
    finished_at: typeof run.finished_at === 'string' ? run.finished_at : undefined,
    input: isRecord(run.input) ? run.input : {},
    output: isRecord(run.output) ? run.output : {},
    error: isRecord(run.error) ? run.error : null,
    evidence_refs: Array.isArray(run.evidence_refs) ? run.evidence_refs : [],
  }));
};

const buildReactNodeData = (
  task: ZentexTask,
  run: ReactGraphNodeRun,
  category: string,
): TaskWorkflowNodeData => {
  const runtimePayload = {
    task_id: task.task_id,
    node_id: run.node_id,
    attempt: run.attempt,
    status: run.status,
    started_at: run.started_at,
    finished_at: run.finished_at,
    evidence_refs: run.evidence_refs,
  };
  const errorReason = firstReadableValue(run.error?.message, run.error?.code, run.error);
  return {
    title: run.node_id || 'react_node',
    category,
    taskId: task.task_id,
    status: run.status || task.status,
    executor: task.target_id || EMPTY_VALUE,
    startedAt: formatTaskDateTime(run.started_at || null),
    finishedAt: formatTaskDateTime(run.finished_at || null),
    inputSummary: shortText(run.input),
    outputSummary: shortText(run.error || run.output || run.status),
    runtimeSummary: shortText(runtimePayload),
    errorReason,
    inputPayload: run.input || {},
    outputPayload: {
      output: run.output || {},
      error: run.error || null,
    },
    runtimePayload,
    logs: [],
  };
};

const edgeStyle = {
  stroke: 'rgba(15,23,42,0.32)',
  strokeWidth: 1.7,
};

function FlowNodeCard({ id, data }: NodeProps<Node<TaskWorkflowNodeData>>) {
  return (
    <Card
      variant="outlined"
      data-testid={`task-workflow-node-${id}`}
      sx={{
        width: 310,
        borderRadius: 2,
        borderColor: statusBorder(String(data.status)),
        boxShadow: '0 14px 32px rgba(15,23,42,0.08)',
        bgcolor: 'background.paper',
      }}
    >
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
        <Stack spacing={1}>
          <Stack direction="row" justifyContent="space-between" spacing={1} alignItems="flex-start">
            <Stack spacing={0.35} sx={{ minWidth: 0 }}>
              <Typography variant="overline" color="text.secondary" sx={{ lineHeight: 1 }}>
                {data.category}
              </Typography>
              <Typography variant="subtitle2" sx={{ fontWeight: 800, wordBreak: 'break-word' }}>
                {data.title}
              </Typography>
            </Stack>
            <Chip label={data.status} size="small" color={statusColor(String(data.status))} />
          </Stack>
          {data.taskId ? (
            <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
              {data.taskId}
            </Typography>
          ) : null}
          <Divider />
          <Stack spacing={0.75}>
            <NodeSection title="tasks.workflowInput" value={data.inputSummary} />
            <NodeSection title="tasks.workflowOutput" value={data.outputSummary} />
            <NodeSection title="tasks.workflowRun" value={data.runtimeSummary} />
          </Stack>
          {data.errorReason !== EMPTY_VALUE ? (
            <Alert severity="error" sx={{ py: 0 }} data-testid={`task-workflow-node-error-${id}`}>
              {data.errorReason}
            </Alert>
          ) : null}
        </Stack>
      </CardContent>
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </Card>
  );
}

function NodeSection({ title, value }: { title: string; value: string }) {
  const { t } = useTranslation();
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>
        {t(title)}
      </Typography>
      <Typography variant="body2" sx={{ wordBreak: 'break-word' }}>
        {value || EMPTY_VALUE}
      </Typography>
    </Box>
  );
}

const nodeTypes = {
  taskWorkflowNode: FlowNodeCard,
};

const buildWorkflowGraph = ({
  detail,
  logsByTaskId,
  t,
}: {
  detail: TaskDetailData;
  logsByTaskId: Record<string, TaskAuditLog[]>;
  t: ReturnType<typeof useTranslation>['t'];
}): { nodes: Node<TaskWorkflowNodeData>[]; edges: Edge[] } => {
  const nodes: Node<TaskWorkflowNodeData>[] = [];
  const edges: Edge[] = [];
  const tasks = [detail.task, ...(detail.subtasks || [])];
  const taskIds = new Set(tasks.map((task) => task.task_id));
  const reactTerminalByTaskId: Record<string, string> = {};
  const startId = 'workflow-start';
  const rootId = taskNodeId(detail.task.task_id);

  nodes.push({
    id: startId,
    type: 'taskWorkflowNode',
    position: { x: 0, y: 190 },
    data: buildBoundaryNodeData(
      t('tasks.workflowStartNode'),
      t('tasks.workflowStartTitle'),
      'completed',
      {
        task_id: detail.task.task_id,
        dependencies: detail.dependencies,
      },
      {
        subtask_count: detail.subtask_count,
        statistics: detail.statistics,
      },
    ),
    draggable: false,
  });

  nodes.push({
    id: rootId,
    type: 'taskWorkflowNode',
    position: { x: 390, y: 190 },
    data: buildTaskNodeData(detail.task, t('tasks.workflowRootNode'), logsByTaskId[detail.task.task_id] || [], t),
    draggable: false,
  });

  edges.push({
    id: `${startId}-${rootId}`,
    source: startId,
    target: rootId,
    type: 'smoothstep',
    markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
    style: edgeStyle,
    animated: ACTIVE_STATUSES.has(detail.task.status),
  });

  const subtasks = detail.subtasks || [];
  subtasks.forEach((subtask, index) => {
    const nodeId = taskNodeId(subtask.task_id);
    nodes.push({
      id: nodeId,
      type: 'taskWorkflowNode',
      position: { x: 790 + Math.floor(index / 4) * 370, y: 30 + (index % 4) * 220 },
      data: buildTaskNodeData(subtask, t('tasks.workflowSubtaskNode'), logsByTaskId[subtask.task_id] || [], t),
      draggable: false,
    });

    const declaredDependency = (subtask.depends_on || []).find((dependencyId) => taskIds.has(dependencyId));
    const sourceTaskId = declaredDependency || subtask.parent_task_id || detail.task.task_id;
    const sourceId = taskIds.has(sourceTaskId) ? taskNodeId(sourceTaskId) : rootId;
    edges.push({
      id: `${sourceId}-${nodeId}`,
      source: sourceId,
      target: nodeId,
      type: 'smoothstep',
      markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
      style: edgeStyle,
      animated: ACTIVE_STATUSES.has(subtask.status),
    });
  });

  tasks.forEach((task, taskIndex) => {
    const graphRuns = extractReactGraphRuns(task);
    if (graphRuns.length === 0) {
      return;
    }
    const y = 520 + taskIndex * 240;
    const taskSourceId = taskNodeId(task.task_id);
    graphRuns.forEach((run, runIndex) => {
      const nodeId = reactNodeId(task.task_id, runIndex, run);
      nodes.push({
        id: nodeId,
        type: 'taskWorkflowNode',
        position: { x: 390 + runIndex * 370, y },
        data: buildReactNodeData(task, run, t('tasks.workflowReactNode')),
        draggable: false,
      });

      edges.push({
        id: `${runIndex === 0 ? taskSourceId : reactNodeId(task.task_id, runIndex - 1, graphRuns[runIndex - 1])}-${nodeId}`,
        source: runIndex === 0 ? taskSourceId : reactNodeId(task.task_id, runIndex - 1, graphRuns[runIndex - 1]),
        target: nodeId,
        type: 'smoothstep',
        markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
        style: {
          ...edgeStyle,
          stroke: 'rgba(2,132,199,0.5)',
        },
        animated: ACTIVE_STATUSES.has(String(run.status || task.status)),
      });
      reactTerminalByTaskId[task.task_id] = nodeId;
    });
  });

  const lastColumn = subtasks.length > 0 ? 790 + Math.floor((subtasks.length - 1) / 4) * 370 : 790;
  const outcomeId = 'workflow-outcome';
  nodes.push({
    id: outcomeId,
    type: 'taskWorkflowNode',
    position: { x: lastColumn + 390, y: 190 },
    data: buildBoundaryNodeData(
      t('tasks.workflowOutcomeNode'),
      t('tasks.workflowOutcomeTitle'),
      detail.task.status,
      {
        task_id: detail.task.task_id,
        dependents: detail.dependents,
      },
      {
        status: detail.task.status,
        progress: detail.task.progress,
        completed_subtasks: detail.statistics?.completed_subtasks,
        failed_subtasks: detail.statistics?.failed_subtasks,
        root_output: parseMaybeJson(detail.task.execution_output),
        root_error: detail.task.last_error,
      },
    ),
    draggable: false,
  });

  const terminalSources = subtasks.length > 0
    ? subtasks.map((subtask) => reactTerminalByTaskId[subtask.task_id] || taskNodeId(subtask.task_id))
    : [reactTerminalByTaskId[detail.task.task_id] || rootId];
  terminalSources.forEach((sourceId) => {
    edges.push({
      id: `${sourceId}-${outcomeId}`,
      source: sourceId,
      target: outcomeId,
      type: 'smoothstep',
      markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
      style: edgeStyle,
      animated: ACTIVE_STATUSES.has(detail.task.status),
    });
  });

  return { nodes, edges };
};

const fetchTaskLogs = async (taskId: string): Promise<TaskAuditLog[]> => {
  const response = await fetch(`/api/web/tasks/${taskId}/logs?limit=50`);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  const payload: TaskLogsResponse = await response.json();
  return payload.items || [];
};

function JsonBlock({ value }: { value: unknown }) {
  return (
    <Box
      component="pre"
      sx={{
        m: 0,
        p: 1.25,
        borderRadius: 1,
        bgcolor: 'rgba(15,23,42,0.04)',
        border: '1px solid',
        borderColor: 'divider',
        fontFamily: 'monospace',
        fontSize: 12,
        lineHeight: 1.55,
        overflow: 'auto',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        maxHeight: 260,
      }}
    >
      {compactJson(value)}
    </Box>
  );
}

function DetailSection({ title, value }: { title: string; value: unknown }) {
  return (
    <Stack spacing={1}>
      <Typography variant="subtitle2">{title}</Typography>
      <JsonBlock value={value} />
    </Stack>
  );
}

export default function TaskWorkflowPage() {
  const { t } = useTranslation();
  const { task_id } = useParams<{ task_id: string }>();
  const [detail, setDetail] = useState<TaskDetailData | null>(null);
  const [logsByTaskId, setLogsByTaskId] = useState<Record<string, TaskAuditLog[]>>({});
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      if (!task_id) {
        setError(t('tasks.idNotFound'));
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const detailResponse = await fetch(`/api/web/tasks/${task_id}/detail`);
        if (!detailResponse.ok) {
          throw new Error(`${t('tasks.workflowLoadFailed')}（HTTP ${detailResponse.status}）`);
        }
        const nextDetail: TaskDetailData = await detailResponse.json();
        const taskIds = [nextDetail.task.task_id, ...(nextDetail.subtasks || []).map((subtask) => subtask.task_id)];
        const logPairs = await Promise.all(
          taskIds.map(async (id) => [id, await fetchTaskLogs(id)] as const),
        );
        if (!cancelled) {
          setDetail(nextDetail);
          setLogsByTaskId(Object.fromEntries(logPairs));
          setSelectedNodeId(taskNodeId(nextDetail.task.task_id));
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : t('tasks.workflowLoadFailed'));
          setDetail(null);
          setLogsByTaskId({});
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [task_id, t]);

  const flowGraph = useMemo(() => {
    if (!detail) {
      return { nodes: [], edges: [] };
    }
    return buildWorkflowGraph({ detail, logsByTaskId, t });
  }, [detail, logsByTaskId, t]);

  const selectedNode = useMemo(() => {
    return flowGraph.nodes.find((node) => node.id === selectedNodeId) || flowGraph.nodes[0] || null;
  }, [flowGraph.nodes, selectedNodeId]);

  if (loading) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, p: 3 }}>
        <CircularProgress size={24} />
        <Typography variant="body2" color="text.secondary">
          {t('tasks.workflowLoading')}
        </Typography>
      </Box>
    );
  }

  if (error || !detail) {
    return (
      <Box sx={{ p: 3 }} data-testid="task-workflow-error">
        <Alert severity="error">
          <AlertTitle>{t('tasks.workflowLoadFailed')}</AlertTitle>
          {error || t('tasks.notFound')}
        </Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }} data-testid="task-workflow-page">
      <Stack direction={{ xs: 'column', lg: 'row' }} justifyContent="space-between" spacing={2}>
        <Box>
          <Typography variant="h4" component="h1" gutterBottom>
            {t('tasks.workflowTitle')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t('tasks.workflowSubtitle', { taskId: detail.task.task_id })}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
          <Button component={RouterLink} to="/console/tasks" startIcon={<BackIcon />} variant="outlined">
            {t('tasks.backToList')}
          </Button>
          <Button component={RouterLink} to={`/console/tasks/${detail.task.task_id}`} variant="outlined">
            {t('tasks.viewDetails')}
          </Button>
          <Button
            component={RouterLink}
            to={`/console/tasks/${detail.task.task_id}/logs`}
            startIcon={<LogsIcon />}
            variant="outlined"
          >
            {t('tasks.logs.viewTaskLogs')}
          </Button>
        </Stack>
      </Stack>

      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
        <StatusChip status={detail.task.status} />
        <Chip label={`${t('tasks.progress')}: ${detail.task.progress}%`} variant="outlined" />
        <Chip label={`${t('tasks.subtasks')}: ${detail.subtask_count}`} variant="outlined" />
        <Chip label={`${t('tasks.executor')}: ${formatExecutionParty(detail.task, t)}`} variant="outlined" />
      </Stack>

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', xl: 'minmax(720px, 1fr) 420px' },
          gap: 2,
          minHeight: 760,
        }}
      >
        <Box
          data-testid="task-workflow-canvas"
          sx={{
            height: { xs: 640, xl: 760 },
            borderRadius: 2,
            border: '1px solid',
            borderColor: 'divider',
            overflow: 'hidden',
            bgcolor: '#f8fafc',
          }}
        >
          <ReactFlow
            nodes={flowGraph.nodes}
            edges={flowGraph.edges}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.18, minZoom: 0.45 }}
            proOptions={{ hideAttribution: true }}
            nodesDraggable={false}
            nodesConnectable={false}
            zoomOnDoubleClick={false}
            minZoom={0.3}
            maxZoom={1.35}
            onNodeClick={(_event, node) => setSelectedNodeId(node.id)}
          >
            <Background gap={24} size={1} color="rgba(15,23,42,0.12)" />
            <MiniMap pannable zoomable nodeStrokeWidth={3} />
            <Controls showInteractive={false} />
          </ReactFlow>
        </Box>

        <Card variant="outlined" data-testid="task-workflow-selected-node">
          <CardContent>
            {selectedNode ? (
              <Stack spacing={2}>
                <Stack spacing={0.75}>
                  <Typography variant="overline" color="text.secondary">
                    {t('tasks.workflowSelectedNode')}
                  </Typography>
                  <Typography variant="h6">{selectedNode.data.title}</Typography>
                  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                    <Chip label={selectedNode.data.category} size="small" variant="outlined" />
                    <Chip label={selectedNode.data.status} size="small" color={statusColor(selectedNode.data.status)} />
                  </Stack>
                </Stack>
                {selectedNode.data.errorReason !== EMPTY_VALUE ? (
                  <Alert severity="error">
                    <AlertTitle>{t('tasks.exceptionReason')}</AlertTitle>
                    {selectedNode.data.errorReason}
                  </Alert>
                ) : null}
                <Stack spacing={1}>
                  <Typography variant="subtitle2">{t('tasks.workflowRun')}</Typography>
                  <Typography variant="body2">{selectedNode.data.runtimeSummary}</Typography>
                </Stack>
                <DetailSection title={t('tasks.workflowInput')} value={selectedNode.data.inputPayload} />
                <DetailSection title={t('tasks.workflowOutput')} value={selectedNode.data.outputPayload} />
                <DetailSection title={t('tasks.workflowRuntime')} value={selectedNode.data.runtimePayload} />
              </Stack>
            ) : (
              <Typography variant="body2" color="text.secondary">
                {t('tasks.workflowNoSelectedNode')}
              </Typography>
            )}
          </CardContent>
        </Card>
      </Box>
    </Box>
  );
}
