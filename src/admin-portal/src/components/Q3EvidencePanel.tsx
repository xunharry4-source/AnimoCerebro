import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  Grid,
  List,
  ListItem,
  ListItemText,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { Q3AssetRow, Q3PreprocessedEvidence, Q3WhatDoIHaveInferenceView, LLMTracePayloadView } from "../pages/nine-questions/nineQuestionsApi";
import LLMTracePanel from "./LLMTracePanel";

function getStatusColor(status: string): "success" | "warning" | "error" | "default" {
  const s = status.toLowerCase();
  if (s === "充沛" || s === "abundant" || s === "healthy" || s === "sufficient") return "success";
  if (s === "降级" || s === "degraded" || s === "warning") return "warning";
  if (s === "匮乏" || s === "scarce" || s === "error" || s === "critical" || s === "critically_lacking") return "error";
  return "default";
}

function AssetTable({
  title,
  rows,
}: {
  title: string;
  rows: Q3AssetRow[];
}) {
  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="subtitle2" gutterBottom>{title}</Typography>
      {rows.length > 0 ? (
        <TableContainer sx={{ border: 1, borderColor: "divider", borderRadius: 1 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontWeight: 700 }}>名称</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>介绍</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>功能说明</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell sx={{ whiteSpace: "nowrap", fontWeight: 600 }}>{row.name}</TableCell>
                  <TableCell>{row.introduction}</TableCell>
                  <TableCell>{row.function_description}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      ) : (
        <Typography variant="body2" color="text.secondary">无可展示资产</Typography>
      )}
    </Box>
  );
}

export function Q3EvidencePanel({
  evidence,
  inference,
  providerName,
  elapsedMs = 0,
  trace,
}: {
  evidence: Q3PreprocessedEvidence;
  inference: Q3WhatDoIHaveInferenceView | null | undefined;
  providerName?: string | null;
  elapsedMs?: number;
  trace?: LLMTracePayloadView | null;
}) {
  const connectedAgents = evidence.tools_agents.connected_agents.filter(
    (agent) => String(agent.status || "").toLowerCase() !== "offline",
  );
  const cognitiveToolRows = evidence.tools_agents.cognitive_tool_rows || [];
  const executionToolRows = evidence.tools_agents.execution_tool_rows || [];
  const connectedAgentRows = evidence.tools_agents.connected_agent_rows || [];
  return (
    <Grid container spacing={3} sx={{ mt: 0.5 }}>
      {/* 0. 推理元数据 (Transparency Metadata) */}
      {(providerName || elapsedMs > 0) && (
        <Grid item xs={12}>
          <Box sx={{ display: "flex", gap: 1, mb: 1 }}>
            {providerName && <Chip label={`Resource Engine: ${providerName}`} size="small" variant="outlined" color="info" />}
            {elapsedMs > 0 && <Chip label={`Latency: ${elapsedMs}ms`} size="small" variant="outlined" />}
          </Box>
        </Grid>
      )}
      {/* 1. 工作区与权限区 */}
      <Grid size={{ xs: 12, md: 6 }}>
        <Card variant="outlined" sx={{ height: "100%" }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              工作区与权限审计
            </Typography>
            <Typography variant="subtitle2" gutterBottom>
              可用工作区 (Workspaces)
            </Typography>
            <List dense sx={{ bgcolor: "action.hover", borderRadius: 1, mb: 2 }}>
              {evidence.workspace_permission.workspaces.map((ws, i) => (
                <ListItem key={i} divider={i < evidence.workspace_permission.workspaces.length - 1}>
                  <ListItemText primary={ws} />
                </ListItem>
              ))}
              {evidence.workspace_permission.workspaces.length === 0 && (
                <ListItem><ListItemText primary="无可用工作区" /></ListItem>
              )}
            </List>
            <Typography variant="subtitle2" gutterBottom>
              租户权限与执行令牌
            </Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              {evidence.workspace_permission.tenant_permissions.map((p, i) => (
                <Chip key={`p-${i}`} label={p} size="small" component="span" />
              ))}
              {evidence.workspace_permission.execution_tokens.map((t, i) => (
                <Chip key={`t-${i}`} label={t} size="small" color="info" variant="outlined" component="span" />
              ))}
              {evidence.workspace_permission.tenant_permissions.length === 0 &&
               evidence.workspace_permission.execution_tokens.length === 0 && (
                <Typography variant="body2" color="text.secondary">无显式权限令牌</Typography>
              )}
            </Stack>
          </CardContent>
        </Card>
      </Grid>

      {/* 2. 工具与 Agent 区 */}
      <Grid size={{ xs: 12, md: 6 }}>
        <Card variant="outlined" sx={{ height: "100%" }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              工具与 Agent 资产
            </Typography>
            <AssetTable title="认知工具" rows={cognitiveToolRows} />
            <AssetTable title="执行工具" rows={executionToolRows} />
            <AssetTable
              title="已连接 Agent"
              rows={
                connectedAgentRows.length > 0
                  ? connectedAgentRows
                  : connectedAgents.map((agent) => ({
                      id: String(agent.id || agent.name || "unknown-agent"),
                      name: String(agent.name || agent.id || "Unknown Agent"),
                      introduction: String(agent.summary || agent.description || "当前已连接的协作 Agent。"),
                      function_description: String(agent.role || agent.scope || agent.status || "承担协作或执行支持。"),
                    }))
              }
            />
          </CardContent>
        </Card>
      </Grid>

      {/* 3. 记忆与策略区 (绝对红线) */}
      <Grid size={{ xs: 12 }}>
        <Card variant="outlined">
          <CardContent>
            <Typography variant="h6" gutterBottom>
              记忆与策略存量 (Memory & Strategy)
            </Typography>
            <Stack spacing={1.5}>
              <Accordion defaultExpanded={false} data-testid="q3-memory-accordion">
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="subtitle2">历史经验记录 (Experience Logs)</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <Stack spacing={1}>
                    {evidence.memory_strategy.experience_logs.map((log, i) => (
                      <Box key={i} sx={{ p: 1.5, bgcolor: "action.hover", borderRadius: 1 }}>
                        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", fontFamily: "monospace", fontSize: "0.85rem" }}>
                          {log}
                        </Typography>
                      </Box>
                    ))}
                    {evidence.memory_strategy.experience_logs.length === 0 && (
                      <Typography variant="body2" color="text.secondary">无历史经验记录</Typography>
                    )}
                  </Stack>
                </AccordionDetails>
              </Accordion>

              <Accordion defaultExpanded={false} data-testid="q3-strategy-accordion">
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="subtitle2">生效策略补丁 (Strategy Patches)</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <Stack spacing={1}>
                    {evidence.memory_strategy.strategy_patches.map((patch, i) => (
                      <Box key={i} sx={{ p: 1.5, bgcolor: "action.hover", borderRadius: 1 }}>
                        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", fontFamily: "monospace", fontSize: "0.85rem" }}>
                          {patch}
                        </Typography>
                      </Box>
                    ))}
                    {evidence.memory_strategy.strategy_patches.length === 0 && (
                      <Typography variant="body2" color="text.secondary">无生效策略补丁</Typography>
                    )}
                  </Stack>
                </AccordionDetails>
              </Accordion>
            </Stack>
          </CardContent>
        </Card>
      </Grid>

      {/* 4. 充沛度终极评估区 */}
      <Grid size={{ xs: 12 }}>
        <Card variant="outlined" sx={{ borderColor: "info.main", bgcolor: "rgba(2, 136, 209, 0.02)" }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              资源充沛度最终评估 (Resource Sufficiency)
            </Typography>
            {inference ? (
              <Stack spacing={2}>
                <Stack direction="row" alignItems="center" spacing={2}>
                  <Typography variant="subtitle1">当前状态:</Typography>
                  <Chip
                    label={inference.sufficiency_assessment.resource_status_label || inference.sufficiency_assessment.resource_status}
                    color={getStatusColor(inference.sufficiency_assessment.resource_status)}
                    data-testid="q3-status-chip"
                  />
                  {providerName && <Typography variant="caption" color="text.secondary">推断引擎: {providerName}</Typography>}
                  {elapsedMs !== undefined && <Typography variant="caption" color="text.secondary">耗时: {elapsedMs}ms</Typography>}
                </Stack>

                {inference.sufficiency_assessment.resource_status_explanation && (
                  <Alert severity="info">
                    <Typography variant="subtitle2">状态解释:</Typography>
                    <Typography variant="body2">{inference.sufficiency_assessment.resource_status_explanation}</Typography>
                  </Alert>
                )}
                
                {inference.sufficiency_assessment.missing_critical_assets.length > 0 && (
                  <Alert severity="error">
                    <Typography variant="subtitle2">缺失关键资产:</Typography>
                    <List dense>
                      {inference.sufficiency_assessment.missing_critical_assets.map((a, i) => (
                        <ListItem key={i}><ListItemText primary={a} /></ListItem>
                      ))}
                    </List>
                  </Alert>
                )}

                {inference.sufficiency_assessment.bottleneck_node && (
                  <Alert severity="warning">
                    <Typography variant="subtitle2">瓶颈节点:</Typography>
                    <Typography variant="body2">{inference.sufficiency_assessment.bottleneck_node}</Typography>
                  </Alert>
                )}

                {inference.sufficiency_assessment.reasoning_summary && (
                  <Box sx={{ p: 2, borderLeft: 4, borderColor: "primary.main", bgcolor: "action.hover" }}>
                    <Typography variant="subtitle2" gutterBottom>评估摘要</Typography>
                    <Typography variant="body2">{inference.sufficiency_assessment.reasoning_summary}</Typography>
                  </Box>
                )}
              </Stack>
            ) : (
              <Alert severity="warning">推断评估尚未生成</Alert>
            )}
          </CardContent>
        </Card>
      </Grid>

      <Grid size={{ xs: 12 }}>
        <Box data-testid="q3-trace-accordion">
          <LLMTracePanel trace={trace} />
        </Box>
      </Grid>

    </Grid>
  );
}

export default Q3EvidencePanel;
