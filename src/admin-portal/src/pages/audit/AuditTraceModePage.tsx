import { useEffect, useState } from "react";
import { Alert, Box, Button, Card, CardContent, Chip, CircularProgress, Stack, Typography } from "@mui/material";
import { Link as RouterLink, Navigate, useParams } from "react-router-dom";
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

import { fetchAuditTraceGraph, type AuditGraphNodeView, type AuditGraphPayloadView } from "./auditApi";
import LearningDashboard from "../learning/LearningDashboard";
import ReflectionDailyPage from "../reflections/ReflectionDailyPage";
import NineQuestionsWorkflowPage from "../nine-questions/NineQuestionsWorkflowPage";
import ExternalConnectorCenter from "../external-connectors/ExternalConnectorCenter";

type AuditTraceMode = "nine_questions" | "reflection" | "learning" | "external_connectors";
type AuditTraceView = "workflow" | "table";

type AuditFlowNodeData = {
  title: string;
  status: string;
  category: string;
  description: string;
  href?: string | null;
  metrics: Record<string, any>;
};

const MODE_META: Record<
  AuditTraceMode,
  {
    title: string;
    subtitle: string;
    tableLabel: string;
  }
> = {
  nine_questions: {
    title: "基于 9 问开始的审计与溯源",
    subtitle: "从九问执行链追到模块、插件、trace 和恢复动作。",
    tableLabel: "九问执行表格视图",
  },
  reflection: {
    title: "基于反思开始的审计与溯源",
    subtitle: "从反思记录追到对应问题、工作流和 trace。",
    tableLabel: "反思记录表格视图",
  },
  learning: {
    title: "基于学习开始的审计与溯源",
    subtitle: "从学习循环追到相关问题、trace 和系统影响。",
    tableLabel: "学习历史表格视图",
  },
  external_connectors: {
    title: "基于外部连接器开始的审计与溯源",
    subtitle: "从外部连接器真实调用追到任务、插件路径、能力、风险、证据和执行结果。",
    tableLabel: "外部连接器管理视图",
  },
};

function statusColor(status: string): "default" | "success" | "warning" | "info" | "error" {
  if (status === "ready") return "success";
  if (status === "active") return "warning";
  if (status === "trace") return "info";
  if (status === "failed") return "error";
  if (status === "completed") return "success";
  if (status === "running") return "warning";
  return "default";
}

function statusBorder(status: string): string {
  if (["ready", "completed"].includes(status)) return "rgba(46,125,50,0.55)";
  if (["active", "running"].includes(status)) return "rgba(245,124,0,0.6)";
  if (status === "trace") return "rgba(30,136,229,0.58)";
  if (status === "failed") return "rgba(211,47,47,0.58)";
  return "rgba(15,23,42,0.18)";
}

function statusBackground(status: string): string {
  if (["ready", "completed"].includes(status)) {
    return "linear-gradient(180deg, rgba(46,125,50,0.12), rgba(255,255,255,0.98))";
  }
  if (["active", "running"].includes(status)) {
    return "linear-gradient(180deg, rgba(245,124,0,0.14), rgba(255,255,255,0.98))";
  }
  if (status === "trace") {
    return "linear-gradient(180deg, rgba(30,136,229,0.14), rgba(255,255,255,0.98))";
  }
  if (status === "failed") {
    return "linear-gradient(180deg, rgba(211,47,47,0.12), rgba(255,255,255,0.98))";
  }
  return "linear-gradient(180deg, rgba(15,23,42,0.06), rgba(255,255,255,0.98))";
}

function AuditFlowNodeCard({ id, data }: NodeProps<Node<AuditFlowNodeData>>) {
  return (
    <Card
      variant="outlined"
      data-testid={`audit-trace-node-${id}`}
      sx={{
        width: 250,
        borderRadius: 4,
        borderColor: statusBorder(String(data.status)),
        boxShadow: "0 18px 40px rgba(15,23,42,0.08)",
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
            <Chip size="small" label={data.status} color={statusColor(data.status)} />
          </Stack>
          <Typography variant="body2" color="text.secondary">
            {data.description}
          </Typography>
          <Box
            sx={{
              p: 1,
              borderRadius: 2,
              bgcolor: "rgba(15,23,42,0.04)",
              fontSize: 11,
              fontFamily: "monospace",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {JSON.stringify(data.metrics || {}, null, 2)}
          </Box>
          {data.href ? (
            <Button component={RouterLink} to={data.href} size="small" variant="outlined" sx={{ alignSelf: "flex-start" }}>
              进入节点
            </Button>
          ) : null}
        </Stack>
      </CardContent>
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </Card>
  );
}

const nodeTypes = {
  auditFlowNode: AuditFlowNodeCard,
};

function buildAuditFlowGraph(payload: AuditGraphPayloadView): { nodes: Node<AuditFlowNodeData>[]; edges: Edge[] } {
  const nodes: Node<AuditFlowNodeData>[] = [];
  const edges: Edge[] = [];
  const nodeIdMap = new Map<string, string>();

  payload.lanes.forEach((lane, laneIndex) => {
    lane.nodes.forEach((node: AuditGraphNodeView, nodeIndex: number) => {
      const reactNodeId = `${lane.lane_id}-${node.node_id}`;
      nodeIdMap.set(node.node_id, reactNodeId);
      nodes.push({
        id: reactNodeId,
        type: "auditFlowNode",
        position: { x: laneIndex * 360, y: 56 + nodeIndex * 240 },
        data: {
          title: node.title,
          status: node.status,
          category: lane.title,
          description: node.description,
          href: node.href,
          metrics: node.metrics || {},
        },
        draggable: false,
        selectable: false,
      });
    });
  });

  payload.edges.forEach((edge) => {
    const source = nodeIdMap.get(edge.source);
    const target = nodeIdMap.get(edge.target);
    if (!source || !target) {
      return;
    }
    edges.push({
      id: edge.edge_id,
      source,
      target,
      type: "smoothstep",
      label: edge.label || undefined,
      markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
      style: { stroke: "rgba(15,23,42,0.26)", strokeWidth: 1.6 },
      labelStyle: { fill: "rgba(15,23,42,0.68)", fontSize: 12 },
      labelBgStyle: { fill: "rgba(255,255,255,0.9)" },
    });
  });

  return { nodes, edges };
}

function WorkflowCanvas({ payload }: { payload: AuditGraphPayloadView }) {
  const graph = buildAuditFlowGraph(payload);

  return (
    <Box data-testid="audit-trace-workflow-board" sx={{ display: "flex", flexDirection: "column", gap: 2.5 }}>
      <Typography variant="body2" color="text.secondary">
        这里使用 React Flow 按节点工作流方式展示审计链路，起点、驱动、模块、执行、Trace、结果都会变成节点，而不是继续用表格或一列卡片伪装工作流。
      </Typography>
      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
        <Chip label={`数据库事件: ${String(payload.summary?.audit_event_count || 0)}`} color="primary" />
        <Chip label={`数据库 trace: ${String(payload.summary?.model_trace_count || 0)}`} variant="outlined" />
        {payload.database_backed ? <Chip label="已从数据库读取" color="success" variant="outlined" /> : null}
      </Stack>

      <Box
        sx={{
          height: 820,
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
          fitViewOptions={{ padding: 0.16, minZoom: 0.55 }}
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

function isKnownMode(mode: string): mode is AuditTraceMode {
  return Object.prototype.hasOwnProperty.call(MODE_META, mode);
}

function TableView({ mode }: { mode: AuditTraceMode }) {
  if (mode === "nine_questions") return <NineQuestionsWorkflowPage />;
  if (mode === "reflection") return <ReflectionDailyPage />;
  if (mode === "external_connectors") return <ExternalConnectorCenter />;
  return <LearningDashboard />;
}

export default function AuditTraceModePage() {
  const { mode: rawMode, view: rawView } = useParams();
  const mode = rawMode || "";
  const view = rawView as AuditTraceView;

  if (!mode || !view || !["workflow", "table"].includes(view) || (view === "table" && !isKnownMode(mode))) {
    return <Navigate to="/console/audit" replace />;
  }

  const meta = isKnownMode(mode)
    ? MODE_META[mode]
    : {
        title: "审计与溯源",
        subtitle: "从真实 audit_flow 入口查看对应审计链。",
        tableLabel: "表格视图",
      };
  const workflowPath = `/console/audit/${mode}/workflow`;
  const tablePath = `/console/audit/${mode}/table`;
  const [loading, setLoading] = useState(view === "workflow");
  const [error, setError] = useState<string | null>(null);
  const [graphPayload, setGraphPayload] = useState<AuditGraphPayloadView | null>(null);

  useEffect(() => {
    if (view !== "workflow") {
      return;
    }
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const payload = await fetchAuditTraceGraph(mode);
        if (active) {
          setGraphPayload(payload);
        }
      } catch (err: any) {
        if (active) {
          setError(err?.message || "获取审计工作流失败");
          setGraphPayload(null);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [mode, view]);

  const effectiveTitle = graphPayload?.title || meta.title;
  const effectiveSubtitle = graphPayload?.subtitle || meta.subtitle;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }} data-testid="audit-trace-mode-page">
      <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
        <Box>
          <Typography variant="h4" gutterBottom>
            {effectiveTitle}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {effectiveSubtitle}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button component={RouterLink} to="/console/audit" variant="outlined">
            返回起点
          </Button>
          <Button component={RouterLink} to={workflowPath} variant={view === "workflow" ? "contained" : "outlined"}>
            工作流视图
          </Button>
          {isKnownMode(mode) ? (
            <Button component={RouterLink} to={tablePath} variant={view === "table" ? "contained" : "outlined"}>
              表格视图
            </Button>
          ) : null}
        </Stack>
      </Stack>

      {view === "workflow" ? (
        loading ? (
          <Box sx={{ display: "flex", alignItems: "center", gap: 2, py: 4 }}>
            <CircularProgress size={24} />
            <Typography variant="body2" color="text.secondary">
              正在从数据库加载审计链路...
            </Typography>
          </Box>
        ) : error ? (
          <Alert severity="error">{error}</Alert>
        ) : graphPayload ? (
          <WorkflowCanvas payload={graphPayload} />
        ) : (
          <Alert severity="info">当前没有可用的审计链路数据。</Alert>
        )
      ) : (
        isKnownMode(mode) ? <TableView mode={mode} /> : <Alert severity="info">该审计链类型没有表格视图。</Alert>
      )}
    </Box>
  );
}
