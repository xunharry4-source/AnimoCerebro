import { useEffect, useState } from "react";
import {
  Alert,
  AlertTitle,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import { Link as RouterLink, useParams } from "react-router-dom";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import {
  executeNineQuestionRecoveryAction,
  fetchNineQuestionModules,
  fetchNineQuestionRaw,
  fetchNineQuestionSummary,
  getQuestionDisplayLabel,
  rollbackNineQuestionModule,
  retryNineQuestionModule,
  type NineQuestionRecoveryPlan,
  type NineQuestionRecoveryAction,
  type NineQuestionWorkflowDependency,
  type NineQuestionWorkflowModuleRun,
  type NineQuestionWorkflowPluginRun,
} from "./nineQuestionsApi";

type WorkflowNodePayload = {
  title: string;
  status: string;
  category: string;
  description: string;
  errorMessage?: string;
  data?: Record<string, any>;
};

function humanizeIdentifier(value: string): string {
  return value.replaceAll("_", " ").replaceAll("-", " ").trim();
}

function statusColor(status: string): "default" | "success" | "warning" | "error" | "info" {
  if (["completed", "ready"].includes(status)) return "success";
  if (["degraded", "partial_failed", "running", "stale"].includes(status)) return "warning";
  if (["failed"].includes(status)) return "error";
  if (["missing", "not_started", "skipped"].includes(status)) return "default";
  return "info";
}

function statusBorder(status: string): string {
  if (["completed", "ready"].includes(status)) return "rgba(46,125,50,0.55)";
  if (["degraded", "partial_failed", "running", "stale"].includes(status)) return "rgba(245,124,0,0.6)";
  if (["failed"].includes(status)) return "rgba(211,47,47,0.58)";
  return "rgba(15,23,42,0.18)";
}

function statusBackground(status: string): string {
  if (["completed", "ready"].includes(status)) {
    return "linear-gradient(180deg, rgba(46,125,50,0.12), rgba(255,255,255,0.98))";
  }
  if (["degraded", "partial_failed", "running", "stale"].includes(status)) {
    return "linear-gradient(180deg, rgba(245,124,0,0.14), rgba(255,255,255,0.98))";
  }
  if (["failed"].includes(status)) {
    return "linear-gradient(180deg, rgba(211,47,47,0.12), rgba(255,255,255,0.98))";
  }
  return "linear-gradient(180deg, rgba(15,23,42,0.06), rgba(255,255,255,0.98))";
}

function FlowNodeCard({ id, data }: NodeProps<Node<WorkflowNodePayload>>) {
  return (
    <Card
      variant="outlined"
      data-testid={`question-workflow-node-${id}`}
      sx={{
        width: 250,
        borderRadius: 4,
        borderColor: statusBorder(String(data.status)),
        boxShadow: "0 20px 45px rgba(15,23,42,0.08)",
        background: statusBackground(String(data.status)),
      }}
    >
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <CardContent sx={{ p: 1.5, "&:last-child": { pb: 1.5 } }}>
        <Stack spacing={1}>
          <Stack direction="row" justifyContent="space-between" spacing={1} alignItems="flex-start">
            <Stack spacing={0.35}>
              <Typography variant="overline" sx={{ lineHeight: 1, color: "text.secondary" }}>
                {data.category}
              </Typography>
              <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
                {data.title}
              </Typography>
            </Stack>
            <Chip label={data.status} size="small" color={statusColor(String(data.status))} />
          </Stack>
          <Typography variant="body2">{data.description}</Typography>
          {data.errorMessage ? (
            <Alert severity="error" sx={{ py: 0 }}>
              {data.errorMessage}
            </Alert>
          ) : null}
          {data.data && Object.keys(data.data).length > 0 ? (
            <Box
              sx={{
                p: 1,
                borderRadius: 2,
                bgcolor: "rgba(15,23,42,0.05)",
                fontFamily: "monospace",
                fontSize: 11,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {JSON.stringify(data.data, null, 2)}
            </Box>
          ) : null}
        </Stack>
      </CardContent>
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </Card>
  );
}

function buildModuleNodes(
  modulesPayload: Record<string, any> | null,
  executionDiagnosis: Record<string, any> | null,
): WorkflowNodePayload[] {
  if (Array.isArray(executionDiagnosis?.module_runs) && executionDiagnosis.module_runs.length > 0) {
    return (executionDiagnosis.module_runs as NineQuestionWorkflowModuleRun[]).map((run) => ({
      title: humanizeIdentifier(run.module_id),
      status: String(run.status || "missing"),
      category: "Module",
      description: run.used_fallback ? "该节点使用了 fallback" : String(run.source || "结构化模块诊断"),
      errorMessage: String(run.error_message || ""),
      data: {
        module_id: run.module_id,
        error_code: run.error_code,
        started_at: run.started_at,
        finished_at: run.finished_at,
      },
    }));
  }

  const modules = modulesPayload?.modules || {};
  return Object.entries(modules).map(([moduleId, payload]: [string, any]) => ({
    title: humanizeIdentifier(moduleId),
    status: String(payload?.status || "missing"),
    category: "Module",
    description: String(payload?.error || payload?.error_message || payload?.data?.status || "模块结果已记录"),
    errorMessage: String(payload?.error || payload?.error_message || ""),
    data: {
      module_id: moduleId,
      ...(payload?.data || {}),
    },
  }));
}

function toDependencyNode(dependency: NineQuestionWorkflowDependency): WorkflowNodePayload {
  return {
    title: humanizeIdentifier(dependency.dependency_id),
    status: dependency.status,
    category: dependency.required ? "Dependency / Required" : "Dependency / Optional",
    description: dependency.message || (dependency.required ? "required" : "optional"),
    data: { required: dependency.required },
  };
}

function toPluginNode(pluginRun: NineQuestionWorkflowPluginRun): WorkflowNodePayload {
  return {
    title: String(pluginRun.plugin_id),
    status: String(pluginRun.status || "missing"),
    category: "Plugin / Service",
    description: `${String(pluginRun.feature_code || "-")} | ${pluginRun.attempted ? "attempted" : "not attempted"}`,
    errorMessage: String(pluginRun.error_message || ""),
    data: {
      expected: pluginRun.expected,
      attempted: pluginRun.attempted,
      duration_ms: pluginRun.duration_ms,
      output_summary: pluginRun.output_summary,
    },
  };
}

function toRecoveryNode(action: any): WorkflowNodePayload {
  return {
    title: action.label,
    status: action.executable ? "completed" : "degraded",
    category: "Recovery",
    description: `${action.kind} | ${action.scope} | ${action.target}`,
    data: {
      executable: action.executable,
      method: action.method,
      path: action.path,
      reason: action.reason,
    },
  };
}

function appendColumnNodes(
  nodes: Node<WorkflowNodePayload>[],
  edges: Edge[],
  columnKey: string,
  items: WorkflowNodePayload[],
  x: number,
  previousIds: string[],
  emptyText: string,
): string[] {
  const sourceIds = previousIds.length > 0 ? previousIds : [];
  const nextIds: string[] = [];
  const payloads = items.length > 0
    ? items
    : [
        {
          title: "No data",
          status: "missing",
          category: columnKey,
          description: emptyText,
          data: {},
        },
      ];

  payloads.forEach((payload, index) => {
    const nodeId = `${columnKey}-${index}`;
    nodes.push({
      id: nodeId,
      type: "workflowNode",
      position: { x, y: 40 + index * 230 },
      data: payload,
      draggable: false,
      selectable: false,
    });
    nextIds.push(nodeId);
    sourceIds.forEach((sourceId, sourceIndex) => {
      if (index === 0 || sourceIndex === 0) {
        edges.push({
          id: `${sourceId}-${nodeId}`,
          source: sourceId,
          target: nodeId,
          type: "smoothstep",
          animated: payload.status === "running",
          markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
          style: { stroke: "rgba(15,23,42,0.26)", strokeWidth: 1.6 },
        });
      }
    });
  });

  return nextIds;
}

function buildFlowGraph({
  qId,
  currentStatus,
  executionDiagnosis,
  rawPayload,
  moduleNodes,
  pluginRuns,
  upstreamDependencies,
  recoveryPlan,
}: {
  qId: string;
  currentStatus: string;
  executionDiagnosis: Record<string, any> | null;
  rawPayload: Record<string, any> | null;
  moduleNodes: WorkflowNodePayload[];
  pluginRuns: NineQuestionWorkflowPluginRun[];
  upstreamDependencies: NineQuestionWorkflowDependency[];
  recoveryPlan: NineQuestionRecoveryPlan | null;
}): { nodes: Node<WorkflowNodePayload>[]; edges: Edge[] } {
  const nodes: Node<WorkflowNodePayload>[] = [];
  const edges: Edge[] = [];

  const startId = `${qId}-start`;
  nodes.push({
    id: startId,
    type: "workflowNode",
    position: { x: 0, y: 180 },
    data: {
      title: `${qId.toUpperCase()} Start`,
      status: "completed",
      category: "Start",
      description: executionDiagnosis?.diagnosis_message
        ? `入口已进入，当前诊断：${String(executionDiagnosis.diagnosis_message)}`
        : "从当前问题详情进入内部执行链。",
      data: {
        trace_id: rawPayload?.trace_id || null,
      },
    },
    draggable: false,
    selectable: false,
  });

  let prevIds = [startId];
  prevIds = appendColumnNodes(
    nodes,
    edges,
    "dependency",
    upstreamDependencies.map(toDependencyNode),
    340,
    prevIds,
    "当前没有上游依赖节点。",
  );
  prevIds = appendColumnNodes(
    nodes,
    edges,
    "module",
    moduleNodes,
    700,
    prevIds,
    "当前没有可视化模块节点。",
  );
  prevIds = appendColumnNodes(
    nodes,
    edges,
    "plugin",
    pluginRuns.map(toPluginNode),
    1060,
    prevIds,
    "当前没有插件执行记录。",
  );
  prevIds = appendColumnNodes(
    nodes,
    edges,
    "recovery",
    recoveryPlan ? recoveryPlan.actions.map(toRecoveryNode) : [],
    1420,
    prevIds,
    "当前没有恢复动作。",
  );

  const outcomeId = `${qId}-outcome`;
  nodes.push({
    id: outcomeId,
    type: "workflowNode",
    position: { x: 1780, y: 180 },
    data: {
      title: `${qId.toUpperCase()} Outcome`,
      status: currentStatus,
      category: "Outcome",
      description: executionDiagnosis?.authenticity_status
        ? `真实性=${String(executionDiagnosis.authenticity_status)}`
        : "当前没有结构化真实性结论。",
      data: {
        trace_id: rawPayload?.trace_id,
        used_fallback: executionDiagnosis?.used_fallback,
      },
    },
    draggable: false,
    selectable: false,
  });
  prevIds.forEach((sourceId) => {
    edges.push({
      id: `${sourceId}-${outcomeId}`,
      source: sourceId,
      target: outcomeId,
      type: "smoothstep",
      animated: currentStatus === "running",
      markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
      style: { stroke: "rgba(15,23,42,0.26)", strokeWidth: 1.6 },
    });
  });

  return { nodes, edges };
}

const nodeTypes = {
  workflowNode: FlowNodeCard,
};

export default function NineQuestionWorkflowGraphPage() {
  const { q_id } = useParams();
  const qId = String(q_id || "");
  const [summary, setSummary] = useState<Record<string, any> | null>(null);
  const [rawPayload, setRawPayload] = useState<Record<string, any> | null>(null);
  const [modulesPayload, setModulesPayload] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [moduleActionError, setModuleActionError] = useState<string | null>(null);
  const [runningActionKey, setRunningActionKey] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextSummary, nextRaw, nextModules] = await Promise.all([
        fetchNineQuestionSummary(qId),
        fetchNineQuestionRaw(qId),
        fetchNineQuestionModules(qId),
      ]);
      setSummary(nextSummary);
      setRawPayload(nextRaw);
      setModulesPayload(nextModules);
    } catch (err: any) {
      setError(err?.message || `${qId.toUpperCase()} 工作流加载失败`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (qId) {
      void load();
    }
  }, [qId]);

  const handleModuleRollback = async (moduleId: string) => {
    setRunningActionKey(`${moduleId}:rollback`);
    setModuleActionError(null);
    try {
      await rollbackNineQuestionModule(qId, moduleId);
      await load();
    } catch (err: any) {
      setModuleActionError(err?.message || `${qId.toUpperCase()}.${moduleId} 模块回滚失败`);
    } finally {
      setRunningActionKey(null);
    }
  };

  const handleModuleRetry = async (moduleId: string, action?: NineQuestionRecoveryAction | null) => {
    setRunningActionKey(`${moduleId}:retry`);
    setModuleActionError(null);
    try {
      if (action?.executable && action.path) {
        await executeNineQuestionRecoveryAction(action);
      } else {
        await retryNineQuestionModule(qId, moduleId);
      }
      await load();
    } catch (err: any) {
      setModuleActionError(err?.message || `${qId.toUpperCase()}.${moduleId} 模块重试失败`);
    } finally {
      setRunningActionKey(null);
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: "flex", alignItems: "center", gap: 2, p: 3 }}>
        <CircularProgress size={24} />
        <Typography variant="body2" color="text.secondary">
          正在加载 {qId.toUpperCase()} 内部工作流...
        </Typography>
      </Box>
    );
  }

  if (error) {
    return (
      <Box sx={{ p: 3 }} data-testid="question-workflow-error">
        <Alert severity="error">
          <AlertTitle>工作流加载失败</AlertTitle>
          {error}
        </Alert>
      </Box>
    );
  }

  const executionDiagnosis = (rawPayload?.context_updates?.[`${qId}_execution_diagnosis`] ||
    modulesPayload?.status?.diagnosis ||
    null) as Record<string, any> | null;
  const moduleNodes = buildModuleNodes(modulesPayload, executionDiagnosis);
  const pluginRuns = (executionDiagnosis?.plugin_runs || []) as NineQuestionWorkflowPluginRun[];
  const upstreamDependencies = (executionDiagnosis?.upstream_dependencies || []) as NineQuestionWorkflowDependency[];
  const recoveryPlan = (executionDiagnosis?.recovery_plan || null) as NineQuestionRecoveryPlan | null;
  const currentStatus = String(summary?.status || modulesPayload?.status?.status || executionDiagnosis?.authenticity_status || "unknown");

  const flowGraph = buildFlowGraph({
    qId,
    currentStatus,
    executionDiagnosis,
    rawPayload,
    moduleNodes,
    pluginRuns,
    upstreamDependencies,
    recoveryPlan,
  });

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }} data-testid="question-workflow-graph-page">
      <Box>
        <Typography variant="h4" gutterBottom>
          {getQuestionDisplayLabel(qId)} 内部工作流图
        </Typography>
        <Typography variant="body2" color="text.secondary">
          这里使用 React Flow 按节点工作流方式展示 Q1-Q9 内部执行链，不再用表格或线性卡片伪装工作流。
        </Typography>
      </Box>

      <Card variant="outlined">
        <CardContent>
          <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              <Chip label={`当前状态: ${currentStatus}`} color={statusColor(currentStatus)} />
              {executionDiagnosis?.authenticity_status ? (
                <Chip label={`真实性: ${String(executionDiagnosis.authenticity_status)}`} variant="outlined" />
              ) : null}
              {executionDiagnosis?.used_fallback ? <Chip label="使用了 fallback" color="warning" variant="outlined" /> : null}
              {rawPayload?.trace_id ? <Chip label={`trace: ${String(rawPayload.trace_id)}`} variant="outlined" sx={{ fontFamily: "monospace" }} /> : null}
            </Stack>
            <Button component={RouterLink} to="/console/audit" variant="outlined">
              返回审计起点
            </Button>
          </Stack>
        </CardContent>
      </Card>

      {executionDiagnosis?.diagnosis_message ? (
        <Alert severity={executionDiagnosis?.authenticity_status === "completed" ? "success" : "warning"}>
          {String(executionDiagnosis.diagnosis_message)}
        </Alert>
      ) : null}

      <Box
        data-testid="question-workflow-canvas"
        sx={{
          height: 760,
          borderRadius: 5,
          border: "1px solid",
          borderColor: "divider",
          overflow: "hidden",
          background:
            "radial-gradient(circle at top left, rgba(30,136,229,0.08), transparent 24%), linear-gradient(180deg, rgba(248,250,252,0.96), rgba(255,255,255,1))",
        }}
      >
        <ReactFlow
          nodes={flowGraph.nodes}
          edges={flowGraph.edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.16, minZoom: 0.6 }}
          proOptions={{ hideAttribution: true }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          zoomOnDoubleClick={false}
          minZoom={0.45}
          maxZoom={1.35}
        >
          <Background gap={24} size={1} color="rgba(15,23,42,0.08)" />
          <Controls showInteractive={false} />
        </ReactFlow>
      </Box>

      <Card variant="outlined">
        <CardContent>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1.25} useFlexGap flexWrap="wrap">
            <Chip label="Start" variant="outlined" />
            <Chip label="Dependency" variant="outlined" />
            <Chip label="Module" variant="outlined" />
            <Chip label="Plugin / Service" variant="outlined" />
            <Chip label="Recovery" variant="outlined" />
            <Chip label="Outcome" variant="outlined" />
          </Stack>
        </CardContent>
      </Card>

      {recoveryPlan ? (
        <Alert severity="info">
          可重试：{recoveryPlan.retriable ? "是" : "否"} | 可回滚：{recoveryPlan.rollback_available ? "是" : "否"} | 局部重试：{recoveryPlan.partial_retry_available ? "是" : "否"} | 局部替换：{recoveryPlan.partial_replace_available ? "是" : "否"}
        </Alert>
      ) : null}

      <Card variant="outlined" data-testid="question-workflow-module-actions">
        <CardContent>
          <Typography variant="h6" gutterBottom>模块动作</Typography>
          <Stack spacing={1}>
            {moduleNodes
              .filter((node) => ["failed", "degraded", "partial_failed", "missing", "stale"].includes(String(node.status)))
              .map((node) => {
                const moduleId = String(node.data?.module_id || "").trim();
                if (!moduleId) return null;
                const moduleRecoveryActions = (recoveryPlan?.actions || []).filter(
                  (action) => String(action.scope || "") === "module" && String(action.target || "") === moduleId,
                );
                const retryAction = moduleRecoveryActions.find((action) =>
                  ["retry", "partial_retry", "partial_replace"].includes(String(action.kind || "")) && action.executable,
                );
                return (
                  <Stack key={moduleId} direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ md: "center" }}>
                    <Typography variant="body2" sx={{ flex: 1, fontFamily: "monospace" }} data-testid={`module-action-row-${moduleId}`}>
                      {moduleId} | {node.status} | {node.errorMessage || node.description}
                    </Typography>
                    {retryAction ? (
                      <Button
                        variant="contained"
                        size="small"
                        disabled={runningActionKey === `${moduleId}:retry`}
                        onClick={() => void handleModuleRetry(moduleId, retryAction)}
                        data-testid={`module-retry-button-${moduleId}`}
                      >
                        {runningActionKey === `${moduleId}:retry` ? "重试中..." : "重试模块"}
                      </Button>
                    ) : null}
                    <Button
                      variant="outlined"
                      size="small"
                      disabled={runningActionKey === `${moduleId}:rollback`}
                      onClick={() => void handleModuleRollback(moduleId)}
                      data-testid={`module-rollback-button-${moduleId}`}
                    >
                      {runningActionKey === `${moduleId}:rollback` ? "回滚中..." : "回滚模块"}
                    </Button>
                  </Stack>
                );
              })}
            {moduleNodes.filter((node) => ["failed", "degraded", "partial_failed", "missing", "stale"].includes(String(node.status))).length === 0 ? (
              <Typography variant="body2" color="text.secondary">当前没有需要操作的异常模块。</Typography>
            ) : null}
            {moduleActionError ? (
              <Alert severity="error" data-testid="module-action-error">{moduleActionError}</Alert>
            ) : null}
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
