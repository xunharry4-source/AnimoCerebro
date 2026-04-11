import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { useTranslation } from "react-i18next";
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
  Tabs,
  Tab,
} from "@mui/material";
import { useState } from "react";
import { Q3AssetRow, Q3PreprocessedEvidence, Q3WhatDoIHaveInferenceView, LLMTracePayloadView } from "../pages/nine-questions/nineQuestionsApi";
import LLMTracePanel from "./LLMTracePanel";

function getStatusColor(status: string): "success" | "warning" | "error" | "default" {
  const s = status.toLowerCase();
  if (s === "充沛" || s === "abundant" || s === "healthy" || s === "sufficient") return "success";
  if (s === "降级" || s === "degraded" || s === "warning") return "warning";
  if (s === "匮乏" || s === "scarce" || s === "error" || s === "critical" || s === "critically_lacking") return "error";
  return "default";
}

const Q3_ASSET_LABEL_MAP: Record<string, string> = {
  execution_domain_tools: "执行域工具 (Execution Domain Tools)",
  connected_agents: "可用协作智能体 (Connected Agents)",
  cognitive_tools: "认知工具 (Cognitive Tools)",
  mcp_servers: "MCP 服务 (MCP Servers)",
  cli_tools: "CLI 工具 (CLI Tools)",
};

const Q3_BOTTLENECK_LABEL_MAP: Record<string, string> = {
  execution_layer: "执行层 (Execution Layer)",
  cognitive_layer: "认知层 (Cognitive Layer)",
  agent_layer: "协作智能体层 (Agent Layer)",
  mcp_layer: "MCP 接入层 (MCP Layer)",
  cli_layer: "CLI 接入层 (CLI Layer)",
};

function humanizeInternalToken(token: string, mapping: Record<string, string>): string {
  const normalized = String(token || "").trim();
  if (!normalized) return "";
  if (mapping[normalized]) return mapping[normalized];
  const titleCase = normalized
    .replace(/[_\-.]+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
  return `${titleCase} (${normalized})`;
}

function AssetTable({
  title,
  rows,
}: {
  title: string;
  rows: Q3AssetRow[];
}) {
  const { t } = useTranslation();
  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="subtitle2" gutterBottom>{title}</Typography>
      {rows.length > 0 ? (
        <TableContainer sx={{ border: 1, borderColor: "divider", borderRadius: 1 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontWeight: 700 }}>{t("nineQuestions.name")}</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>{t("nineQuestions.introduction")}</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>{t("nineQuestions.functionDescription")}</TableCell>
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
        <Typography variant="body2" color="text.secondary">{t("nineQuestions.noAssetsToShow")}</Typography>
      )}
    </Box>
  );
}

function McpServerTable({
  servers,
}: {
  servers: Array<{
    server_id: string;
    transport_type: string;
    status: string;
    tool_count: number;
    tools?: Array<{
      tool_name: string;
      description: string;
      plugin_id: string;
      feature_code: string;
    }>;
  }>;
}) {
  const { t } = useTranslation();
  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="subtitle2" gutterBottom>{t("nineQuestions.mcpServers")}</Typography>
      {servers.length > 0 ? (
        <TableContainer sx={{ border: 1, borderColor: "divider", borderRadius: 1 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontWeight: 700 }}>{t("nineQuestions.serverId")}</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>{t("nineQuestions.transportType")}</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>{t("nineQuestions.toolCount")}</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>{t("nineQuestions.toolList")}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {servers.map((server) => (
                <TableRow key={server.server_id}>
                  <TableCell sx={{ whiteSpace: "nowrap", fontWeight: 600 }}>{server.server_id}</TableCell>
                  <TableCell>{server.transport_type}</TableCell>
                  <TableCell>{server.tool_count}</TableCell>
                  <TableCell>
                    {server.tools && server.tools.length > 0 ? (
                      <Stack direction="column" spacing={0.5}>
                        {server.tools.slice(0, 3).map((tool) => (
                          <Typography key={tool.tool_name} variant="caption" display="block">
                            • {tool.tool_name}: {tool.description}
                          </Typography>
                        ))}
                        {server.tools.length > 3 && (
                          <Typography variant="caption" color="text.secondary">
                            {t("nineQuestions.andMoreTools", { count: server.tools.length - 3 })}
                          </Typography>
                        )}
                      </Stack>
                    ) : (
                      <Typography variant="body2" color="text.secondary">{t("nineQuestions.noTools")}</Typography>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      ) : (
        <Typography variant="body2" color="text.secondary">{t("nineQuestions.noMcpServers")}</Typography>
      )}
    </Box>
  );
}

function CliToolTable({
  tools,
}: {
  tools: Array<{
    command_name: string;
    description: string;
    mapped_domain: string;
    plugin_id: string;
    feature_code: string;
    read_only: boolean;
    status: string;
  }>;
}) {
  const { t } = useTranslation();
  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="subtitle2" gutterBottom>{t("nineQuestions.cliTools")}</Typography>
      {tools.length > 0 ? (
        <TableContainer sx={{ border: 1, borderColor: "divider", borderRadius: 1 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontWeight: 700 }}>{t("nineQuestions.commandName")}</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>{t("nineQuestions.description")}</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>{t("nineQuestions.mappedDomain")}</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>{t("nineQuestions.readOnly")}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {tools.map((tool) => (
                <TableRow key={tool.command_name}>
                  <TableCell sx={{ whiteSpace: "nowrap", fontWeight: 600, fontFamily: "monospace" }}>
                    {tool.command_name}
                  </TableCell>
                  <TableCell>{tool.description}</TableCell>
                  <TableCell>
                    <Chip label={tool.mapped_domain} size="small" variant="outlined" />
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={tool.read_only ? t("common.yes") : t("common.no")}
                      size="small"
                      color={tool.read_only ? "success" : "warning"}
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      ) : (
        <Typography variant="body2" color="text.secondary">{t("nineQuestions.noCliTools")}</Typography>
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
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<number>(0);

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue);
  };

  const connectedAgents = evidence.tools_agents.connected_agents.filter(
    (agent) => String(agent.status || "").toLowerCase() !== "offline",
  );
  const cognitiveToolRows = evidence.tools_agents.cognitive_tool_rows || [];
  const executionToolRows = evidence.tools_agents.execution_tool_rows || [];
  const connectedAgentRows = evidence.tools_agents.connected_agent_rows || [];
  const mcpServers = evidence.tools_agents.mcp_servers || [];
  const cliTools = evidence.tools_agents.cli_tools || [];

  const tabData = [
    {
      label: `${t("nineQuestions.cognitiveTools")} (${cognitiveToolRows.length})`,
      content: <AssetTable title={t("nineQuestions.cognitiveTools")} rows={cognitiveToolRows} />,
    },
    {
      label: `${t("nineQuestions.executionTools")} (${executionToolRows.length})`,
      content: <AssetTable title={t("nineQuestions.executionTools")} rows={executionToolRows} />,
    },
    {
      label: `${t("nineQuestions.agents")} (${connectedAgentRows.length || connectedAgents.length})`,
      content: (
        <AssetTable
          title={t("nineQuestions.connectedAgents")}
          rows={
            connectedAgentRows.length > 0
              ? connectedAgentRows
              : connectedAgents.map((agent) => ({
                  id: String(agent.id || agent.name || "unknown-agent"),
                  name: String(agent.name || agent.id || "Unknown Agent"),
                  introduction: String(agent.summary || agent.description || t("nineQuestions.connectedAgentDesc")),
                  function_description: String(agent.role || agent.scope || t("nineQuestions.agentRoleDesc")),
                }))
          }
        />
      ),
    },
    {
      label: `${t("nineQuestions.mcpServers")} (${mcpServers.length})`,
      content: <McpServerTable servers={mcpServers} />,
    },
    {
      label: `${t("nineQuestions.cliTools")} (${cliTools.length})`,
      content: <CliToolTable tools={cliTools} />,
    },
  ];

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
              {t("nineQuestions.workspacePermissionAudit")}
            </Typography>
            <Typography variant="subtitle2" gutterBottom>
              {t("nineQuestions.availableWorkspaces")}
            </Typography>
            <List dense sx={{ bgcolor: "action.hover", borderRadius: 1, mb: 2 }}>
              {evidence.workspace_permission.workspaces.map((ws, i) => (
                <ListItem key={i} divider={i < evidence.workspace_permission.workspaces.length - 1}>
                  <ListItemText primary={ws} />
                </ListItem>
              ))}
              {evidence.workspace_permission.workspaces.length === 0 && (
                <ListItem><ListItemText primary={t("nineQuestions.noAvailableWorkspaces")} /></ListItem>
              )}
            </List>
            <Typography variant="subtitle2" gutterBottom>
              {t("nineQuestions.tenantPermissionsTokens")}
            </Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              {evidence.workspace_permission.tenant_permissions.map((p, i) => (
                <Chip key={`p-${i}`} label={p} size="small" component="span" />
              ))}
              {evidence.workspace_permission.execution_tokens.map((tToken, i) => (
                <Chip key={`t-${i}`} label={tToken} size="small" color="info" variant="outlined" component="span" />
              ))}
              {evidence.workspace_permission.tenant_permissions.length === 0 &&
               evidence.workspace_permission.execution_tokens.length === 0 && (
                <Typography variant="body2" color="text.secondary">{t("nineQuestions.noExplicitTokens")}</Typography>
              )}
            </Stack>
          </CardContent>
        </Card>
      </Grid>

      {/* 2. 工具与 Agent 区 (Tab 切换) */}
      <Grid size={{ xs: 12 }}>
        <Card variant="outlined">
          <CardContent>
            <Typography variant="h6" gutterBottom>
              {t("nineQuestions.toolsAndAgents")}
            </Typography>
            
            <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}>
              <Tabs
                value={activeTab}
                onChange={handleTabChange}
                aria-label="Q3 asset tabs"
                variant="scrollable"
                scrollButtons="auto"
                allowScrollButtonsMobile
              >
                {tabData.map((tab, index) => (
                  <Tab
                    key={index}
                    label={tab.label}
                    id={`q3-tab-${index}`}
                    aria-controls={`q3-tabpanel-${index}`}
                  />
                ))}
              </Tabs>
            </Box>
            
            {tabData.map((tab, index) => (
              <div
                key={index}
                role="tabpanel"
                hidden={activeTab !== index}
                id={`q3-tabpanel-${index}`}
                aria-labelledby={`q3-tab-${index}`}
              >
                {activeTab === index && (
                  <Box sx={{ pt: 2 }}>
                    {tab.content}
                  </Box>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      </Grid>

      {/* 3. 记忆与策略区 (绝对红线) */}
      <Grid size={{ xs: 12 }}>
        <Card variant="outlined">
          <CardContent>
            <Typography variant="h6" gutterBottom>
              {t("nineQuestions.memoryStrategyStock")}
            </Typography>
            <Stack spacing={1.5}>
              <Accordion defaultExpanded={false} data-testid="q3-memory-accordion">
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="subtitle2">{t("nineQuestions.experienceLogs")}</Typography>
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
                      <Typography variant="body2" color="text.secondary">{t("nineQuestions.noExperienceLogs")}</Typography>
                    )}
                  </Stack>
                </AccordionDetails>
              </Accordion>

              <Accordion defaultExpanded={false} data-testid="q3-strategy-accordion">
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="subtitle2">{t("nineQuestions.strategyPatches")}</Typography>
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
                      <Typography variant="body2" color="text.secondary">{t("nineQuestions.noStrategyPatches")}</Typography>
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
              {t("nineQuestions.resourceSufficiency")}
            </Typography>
            {inference ? (
              <Stack spacing={2}>
                <Stack direction="row" alignItems="center" spacing={2}>
                  <Typography variant="subtitle1">{t("nineQuestions.currentStatus")}:</Typography>
                  <Chip
                    label={inference.sufficiency_assessment.resource_status_label || inference.sufficiency_assessment.resource_status}
                    color={getStatusColor(inference.sufficiency_assessment.resource_status)}
                    data-testid="q3-status-chip"
                  />
                  {providerName && <Typography variant="caption" color="text.secondary">{t("nineQuestions.inferenceEngine")}: {providerName}</Typography>}
                  {elapsedMs !== undefined && <Typography variant="caption" color="text.secondary">{t("nineQuestions.elapsedTime")}: {elapsedMs}ms</Typography>}
                </Stack>

                {inference.sufficiency_assessment.resource_status_explanation && (
                  <Alert severity="info">
                    <Typography variant="subtitle2">{t("nineQuestions.statusExplanation")}:</Typography>
                    <Typography variant="body2">{inference.sufficiency_assessment.resource_status_explanation}</Typography>
                  </Alert>
                )}
                
                {inference.sufficiency_assessment.missing_critical_assets.length > 0 && (
                  <Alert severity="error">
                    <Typography variant="subtitle2">{t("nineQuestions.missingCriticalAssets")}:</Typography>
                    <List dense>
                      {inference.sufficiency_assessment.missing_critical_assets.map((a, i) => (
                        <ListItem key={i}>
                          <ListItemText primary={humanizeInternalToken(a, Q3_ASSET_LABEL_MAP)} />
                        </ListItem>
                      ))}
                    </List>
                  </Alert>
                )}

                {inference.sufficiency_assessment.bottleneck_node && (
                  <Alert severity="warning">
                    <Typography variant="subtitle2">{t("nineQuestions.bottleneckNode")}:</Typography>
                    <Typography variant="body2">
                      {humanizeInternalToken(inference.sufficiency_assessment.bottleneck_node, Q3_BOTTLENECK_LABEL_MAP)}
                    </Typography>
                  </Alert>
                )}

                {inference.sufficiency_assessment.reasoning_summary && (
                  <Box sx={{ p: 2, borderLeft: 4, borderColor: "primary.main", bgcolor: "action.hover" }}>
                    <Typography variant="subtitle2" gutterBottom>{t("nineQuestions.evaluationSummary")}</Typography>
                    <Typography variant="body2">{inference.sufficiency_assessment.reasoning_summary}</Typography>
                  </Box>
                )}
              </Stack>
            ) : (
              <Alert severity="warning">{t("nineQuestions.inferenceNotGenerated")}</Alert>
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
