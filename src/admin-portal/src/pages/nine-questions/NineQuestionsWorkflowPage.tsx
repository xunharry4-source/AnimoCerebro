import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import { Link as RouterLink } from "react-router-dom";
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

import {
  NineQuestionWorkflowPayload,
  NineQuestionWorkflowQuestionStatus,
  fetchNineQuestionWorkflow,
} from "./nineQuestionsApi";

type WorkflowOverviewNodeData = {
  title: string;
  status: string;
  questionId?: string;
  diagnosis: string;
  details: string[];
  to?: string;
};

function statusLabel(status: string): string {
  const mapping: Record<string, string> = {
    completed: "已完成",
    degraded: "降级完成",
    partial_failed: "部分失败",
    failed: "失败",
    running: "执行中",
    not_started: "未开始",
    missing: "缺失",
    skipped: "跳过",
  };
  return mapping[status] || status;
}

function statusColor(
  status: string,
): "default" | "primary" | "secondary" | "error" | "info" | "success" | "warning" {
  switch (status) {
    case "completed":
      return "success";
    case "degraded":
    case "partial_failed":
      return "warning";
    case "failed":
      return "error";
    case "running":
      return "warning";
    case "not_started":
      return "default";
    default:
      return "info";
  }
}

function diagnosisSeverity(
  code: string,
): "info" | "warning" | "error" | "success" {
  if (code === "completed") return "success";
  if (code === "not_started") return "info";
  if (code === "state_committed" || code === "memory_write_missing" || code === "state_write_missing" || code === "execution_incomplete") return "warning";
  if (code === "functional_plugin_unavailable" || code === "plugin_execution_failed" || code === "llm_failed" || code === "state_write_failed" || code === "unknown_failure") {
    return "error";
  }
  return "success";
}

function diagnosisLabel(code: string): string {
  const mapping: Record<string, string> = {
    completed: "执行完成",
    state_committed: "结果已落盘",
    not_started: "未开始",
    functional_plugin_unavailable: "功能插件未执行",
    plugin_execution_failed: "插件执行失败",
    llm_failed: "大模型失败",
    state_write_failed: "状态写入失败",
    state_write_missing: "缺少状态写入",
    memory_write_missing: "缺少记忆写入",
    execution_incomplete: "执行链中断",
    unknown_failure: "未知失败",
  };
  return mapping[code] || code;
}

function nodeBorder(status: string): string {
  if (["completed"].includes(status)) return "rgba(46,125,50,0.55)";
  if (["degraded", "partial_failed", "running"].includes(status)) return "rgba(245,124,0,0.6)";
  if (["failed"].includes(status)) return "rgba(211,47,47,0.58)";
  return "rgba(15,23,42,0.18)";
}

function nodeBackground(status: string): string {
  if (["completed"].includes(status)) {
    return "linear-gradient(180deg, rgba(46,125,50,0.12), rgba(255,255,255,0.98))";
  }
  if (["degraded", "partial_failed", "running"].includes(status)) {
    return "linear-gradient(180deg, rgba(245,124,0,0.14), rgba(255,255,255,0.98))";
  }
  if (["failed"].includes(status)) {
    return "linear-gradient(180deg, rgba(211,47,47,0.12), rgba(255,255,255,0.98))";
  }
  return "linear-gradient(180deg, rgba(15,23,42,0.06), rgba(255,255,255,0.98))";
}

function WorkflowOverviewNode({ id, data }: NodeProps<Node<WorkflowOverviewNodeData>>) {
  return (
    <Card
      variant="outlined"
      data-testid={data.questionId ? `workflow-question-${data.questionId}` : `workflow-node-${id}`}
      sx={{
        width: data.questionId ? 310 : 250,
        borderRadius: 4,
        borderColor: nodeBorder(String(data.status)),
        boxShadow: "0 18px 40px rgba(15,23,42,0.08)",
        background: nodeBackground(String(data.status)),
      }}
    >
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <CardContent sx={{ p: 1.5, "&:last-child": { pb: 1.5 } }}>
        <Stack spacing={1}>
          <Stack direction="row" justifyContent="space-between" spacing={1} alignItems="flex-start">
            <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
              {data.title}
            </Typography>
            <Chip
              label={statusLabel(data.status)}
              color={statusColor(data.status)}
              size="small"
              data-testid={data.questionId ? `workflow-status-${data.questionId}` : undefined}
            />
          </Stack>

          <Alert
            severity={diagnosisSeverity(data.questionId ? data.diagnosis.split("::", 1)[0] : "completed")}
            data-testid={data.questionId ? `workflow-diagnosis-${data.questionId}` : undefined}
            sx={{ py: 0 }}
          >
            {data.questionId ? data.diagnosis.split("::").slice(1).join("::") || data.diagnosis : data.diagnosis}
          </Alert>

          {data.details.map((detail, index) => (
            <Box
              key={`${id}-detail-${index}`}
              sx={{
                px: 1,
                py: 0.75,
                borderRadius: 2,
                bgcolor: "rgba(15,23,42,0.04)",
                fontSize: 12,
                fontFamily: "monospace",
              }}
              data-testid={data.questionId && index === 0 ? `workflow-authenticity-${data.questionId}` : undefined}
            >
              {detail}
            </Box>
          ))}

          {data.to ? (
            <Button component={RouterLink} to={data.to} size="small" variant="outlined" sx={{ alignSelf: "flex-start" }}>
              进入工作流
            </Button>
          ) : null}
        </Stack>
      </CardContent>
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </Card>
  );
}

const nodeTypes = {
  workflowOverviewNode: WorkflowOverviewNode,
};

function buildOverviewGraph(questionRows: NineQuestionWorkflowQuestionStatus[], eventCount: number | undefined) {
  const nodes: Node<WorkflowOverviewNodeData>[] = [];
  const edges: Edge[] = [];

  nodes.push({
    id: "workflow-start",
    type: "workflowOverviewNode",
    position: { x: 0, y: 180 },
    data: {
      title: "九问工作流入口",
      status: "completed",
      diagnosis: "从这里进入 Q1-Q9 总览链路",
      details: [
        "监控页只读视图",
        `Events: ${eventCount ?? 0}`,
      ],
      to: "/console/audit/nine_questions/workflow",
    },
    draggable: false,
    selectable: false,
  });

  let previousId = "workflow-start";
  questionRows.forEach((question, index) => {
    const nodeId = `question-${question.question_id}`;
    nodes.push({
      id: nodeId,
      type: "workflowOverviewNode",
      position: { x: 360 * (index + 1), y: index % 2 === 0 ? 40 : 320 },
      data: {
        title: `${question.question_id.toUpperCase()} · ${question.question_title}`,
        questionId: question.question_id,
        status: question.current_status || "not_started",
        diagnosis: `${question.diagnosis_code}::${diagnosisLabel(question.diagnosis_code)}：${question.diagnosis_message}`,
        details: [
          `真实性: ${statusLabel(question.authenticity_status || question.current_status || "unknown")}`,
          question.used_fallback ? "使用了 fallback" : "未使用 fallback",
          `traces: ${question.trace_count}`,
          question.latest_error ? `error: ${question.latest_error}` : "error: -",
        ],
        to: `/console/nine-questions/${question.question_id}/workflow`,
      },
      draggable: false,
      selectable: false,
    });
    edges.push({
      id: `${previousId}-${nodeId}`,
      source: previousId,
      target: nodeId,
      type: "smoothstep",
      animated: question.current_status === "running",
      markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
      style: { stroke: "rgba(15,23,42,0.26)", strokeWidth: 1.6 },
    });
    previousId = nodeId;
  });

  return { nodes, edges };
}

export default function NineQuestionsWorkflowPage() {
  const [payload, setPayload] = useState<NineQuestionWorkflowPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadWorkflow = async () => {
    setLoading(true);
    setError(null);
    try {
      setPayload(await fetchNineQuestionWorkflow());
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载九问工作流日志失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadWorkflow();
  }, []);

  if (loading) {
    return <CircularProgress data-testid="workflow-loading" />;
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  const questionRows = payload?.questions || [];
  const summaryCounts = payload?.summary_counts || {};
  const summary = {
    completed:
      typeof summaryCounts.completed === "number"
        ? summaryCounts.completed
        : questionRows.filter((item) => item.current_status === "completed").length,
    running:
      typeof summaryCounts.running === "number"
        ? summaryCounts.running
        : questionRows.filter((item) => item.current_status === "running").length,
    failed:
      typeof summaryCounts.failed === "number"
        ? summaryCounts.failed
        : questionRows.filter((item) => item.current_status === "failed").length,
    notStarted:
      typeof summaryCounts.not_started === "number"
        ? summaryCounts.not_started
        : questionRows.filter((item) => item.current_status === "not_started").length,
  };
  const graph = buildOverviewGraph(questionRows, payload?.event_count);

  return (
    <Box data-testid="nine-questions-workflow-page">
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Box>
          <Typography variant="h4" gutterBottom>
            九问工作流总览
          </Typography>
          <Typography variant="body2" color="text.secondary">
            这里改成 React Flow 总览图，Q1-Q9 会按节点方式展示，不再用折叠卡片堆叠。
          </Typography>
          <Typography variant="body2" color="text.secondary">
            监控事件数: {payload?.event_count ?? 0}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" onClick={() => void loadWorkflow()}>
            刷新日志
          </Button>
          <Button component={RouterLink} to="/console/nine-questions" variant="contained">
            返回九问总览
          </Button>
        </Stack>
      </Stack>

      <Alert severity="info" sx={{ mb: 3 }}>
        该页面是九问执行链的监控视图，不承担运行控制职责。页面会按节点展示 Q1-Q9 当前状态、真实性、诊断原因和 fallback，不再靠展开表格和空值猜测。
      </Alert>

      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 3 }}>
        <Chip label={`已完成: ${summary.completed}`} color="success" />
        <Chip label={`执行中: ${summary.running}`} color="warning" />
        <Chip label={`失败: ${summary.failed}`} color="error" />
        <Chip label={`未开始: ${summary.notStarted}`} variant="outlined" />
      </Stack>

      <Box
        data-testid="workflow-overview-canvas"
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
          nodes={graph.nodes}
          edges={graph.edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.18, minZoom: 0.55 }}
          proOptions={{ hideAttribution: true }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          zoomOnDoubleClick={false}
          minZoom={0.4}
          maxZoom={1.35}
        >
          <Background gap={24} size={1} color="rgba(15,23,42,0.08)" />
          <Controls showInteractive={false} />
        </ReactFlow>
      </Box>
    </Box>
  );
}
