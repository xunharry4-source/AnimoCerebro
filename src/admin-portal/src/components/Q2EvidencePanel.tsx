import React, { useState } from "react";
import { Alert, Box, Card, CardContent, Chip, List, ListItem, ListItemText, Stack, Tab, Tabs, Typography } from "@mui/material";
import { Q2PreprocessedEvidence, Q2WhoAmIInferenceView } from "../pages/nine-questions/nineQuestionsApi";

interface Q2EvidencePanelProps {
  evidence: Q2PreprocessedEvidence;
  inference: Q2WhoAmIInferenceView | null | undefined;
  providerName?: string | null;
  elapsedMs?: number;
}

const ASSET_LABELS: Record<string, string> = {
  long_term_memory: "长期记忆",
  cognitive_and_functional_tools: "可用工具",
  connected_agents: "外部 Agent",
  strategy_patches: "策略补丁",
};

function asRecord(value: unknown): Record<string, any> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, any>) : {};
}

function asStringList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item || "").trim()).filter(Boolean);
  if (typeof value === "string" && value.trim()) return [value.trim()];
  return [];
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function hasAssetInventoryData(value: unknown): boolean {
  const inventory = asRecord(value);
  return Boolean(String(inventory.inventory_summary || "").trim())
    || Object.values(inventory).some((item) => Array.isArray(item) && item.length > 0);
}

function assetInventoryRows(assetInventory: Record<string, any>) {
  return Object.entries(ASSET_LABELS).flatMap(([key, label]) => {
    const rawItems = Array.isArray(assetInventory[key]) ? assetInventory[key] : [];
    if (rawItems.length === 0) {
      return [{
        key,
        label,
        name: "",
        description: "",
        source: "",
        pluginCategory: "",
        trustLevel: "",
        validity: "",
      }];
    }
    return rawItems.map((rawItem: unknown, index: number) => {
      const item = asRecord(rawItem);
      return {
        key: `${key}-${index}`,
        label,
        name: String(item.asset_name || ""),
        description: String(item.description || ""),
        source: String(item.source || ""),
        pluginCategory: String(item.plugin_category || ""),
        trustLevel: String(item.trust_level || ""),
        validity: String(item.validity || ""),
      };
    });
  });
}

function rowTitle(item: unknown): string {
  const record = asRecord(item);
  return String(
    record.display_name ||
      record.name ||
      record.id ||
      record.plugin_id ||
      record.feature_code ||
      record.command_name ||
      record.server_id ||
      record.connector_id ||
      record.asset_name ||
      item ||
      "",
  ).trim();
}

function rowDescription(item: unknown): string {
  const record = asRecord(item);
  return String(
    record.description ||
      record.summary ||
      record.status ||
      record.operational_status ||
      record.lifecycle_status ||
      "",
  ).trim();
}

function SimpleRows({ items, emptyText }: { items: unknown[]; emptyText: string }) {
  if (items.length === 0) return <Alert severity="info">{emptyText}</Alert>;
  return (
    <List dense disablePadding>
      {items.map((item, index) => {
        const title = rowTitle(item) || `item-${index + 1}`;
        const description = rowDescription(item);
        return (
          <ListItem key={`${title}-${index}`} divider={index < items.length - 1} sx={{ px: 0 }}>
            <ListItemText
              primary={<Typography variant="body2" fontWeight="bold">{title}</Typography>}
              secondary={description || undefined}
            />
          </ListItem>
        );
      })}
    </List>
  );
}

export const Q2EvidencePanel: React.FC<Q2EvidencePanelProps> = ({
  evidence,
  inference,
  providerName,
  elapsedMs = 0,
}) => {
  const [activeTab, setActiveTab] = useState(0);
  const assetInventory = hasAssetInventoryData(inference?.asset_inventory)
    ? asRecord(inference?.asset_inventory)
    : asRecord(evidence.asset_inventory);
  const sufficiency = asRecord(inference?.sufficiency_assessment);
  const toolsAgents = asRecord(evidence.tools_agents);
  const unifiedInventory = asRecord(toolsAgents.unified_inventory);
  const humanizedInventory = asRecord(toolsAgents.humanized_inventory);
  const memoryStrategy = asRecord(evidence.memory_strategy);
  const rows = assetInventoryRows(assetInventory);
  const missingAssets = asStringList(sufficiency.missing_critical_assets);
  const inventorySummary = String(assetInventory.inventory_summary || "");
  const cognitivePluginRows = asArray(humanizedInventory.cognitive_tool_rows || toolsAgents.cognitive_tool_rows);
  const functionalPluginRows = asArray(humanizedInventory.execution_tool_rows || toolsAgents.execution_tool_rows);
  const fallbackCognitiveTools = asStringList(unifiedInventory.available_cognitive_tools || toolsAgents.cognitive_tools);
  const fallbackExecutionTools = asStringList(unifiedInventory.available_execution_tools || toolsAgents.execution_tools);
  const cognitivePlugins = cognitivePluginRows.length > 0 ? cognitivePluginRows : fallbackCognitiveTools;
  const functionalPlugins = functionalPluginRows.length > 0 ? functionalPluginRows : fallbackExecutionTools;
  const cliTools = asArray(humanizedInventory.cli_tools || toolsAgents.cli_tools);
  const mcpServers = asArray(humanizedInventory.mcp_servers || toolsAgents.mcp_servers);
  const externalConnectors = asArray(humanizedInventory.external_connectors || toolsAgents.external_connectors);
  const functionalAssets = asArray(humanizedInventory.functional_assets || toolsAgents.functional_assets);
  const connectedAgents = asArray(humanizedInventory.connected_agent_rows || toolsAgents.connected_agent_rows || toolsAgents.connected_agents);
  const memoryItems = asStringList(memoryStrategy.experience_logs);
  const strategyItems = asStringList(memoryStrategy.strategy_patches);

  return (
    <Stack spacing={3} sx={{ mt: 2 }}>
      {(providerName || elapsedMs > 0) && (
        <Box sx={{ display: "flex", gap: 1, mb: 1 }}>
          {providerName && <Chip label={`Asset Engine: ${providerName}`} size="small" variant="outlined" color="info" />}
          {elapsedMs > 0 && <Chip label={`Latency: ${elapsedMs}ms`} size="small" variant="outlined" />}
        </Box>
      )}

      <Card variant="outlined" sx={{ borderColor: "primary.main" }}>
        <CardContent>
          <Typography variant="h6" gutterBottom sx={{ fontWeight: "bold" }}>
            Q2 AssetInventory
          </Typography>
          <Tabs
            value={activeTab}
            onChange={(_event, value) => setActiveTab(value)}
            variant="scrollable"
            allowScrollButtonsMobile
            sx={{ mb: 2, borderBottom: 1, borderColor: "divider" }}
          >
            <Tab label="资产盘点" />
            <Tab label={`内部插件 ${cognitivePlugins.length + functionalPlugins.length}`} />
            <Tab label="外部工具" />
            <Tab label="Agent/记忆" />
            <Tab label="资源评估" />
          </Tabs>

          {activeTab === 0 ? (
            <Stack spacing={2}>
              {inventorySummary ? <Alert severity="info">{inventorySummary}</Alert> : null}
              <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" } }}>
                {rows.map((row) => (
                  <Box key={row.key} sx={{ p: 2, border: "1px solid", borderColor: "divider", borderRadius: 1, height: "100%" }}>
                    <Stack spacing={1}>
                      <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
                        <Typography variant="subtitle2">{row.label}</Typography>
                        {row.trustLevel ? <Chip size="small" label={`trust ${row.trustLevel}`} /> : null}
                      </Stack>
                      {row.name ? <Typography variant="body2" fontWeight="bold">{row.name}</Typography> : null}
                      <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                        {row.description || "N/A"}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        source: {row.source || "N/A"} · category: {row.pluginCategory || "N/A"} · trust: {row.trustLevel || "N/A"}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        validity: {row.validity || "N/A"}
                      </Typography>
                    </Stack>
                  </Box>
                ))}
              </Box>
              {rows.every((row) => !row.description) ? (
                <Alert severity="warning">Q2 AssetInventory 尚未写入当前查询结果。</Alert>
              ) : null}
            </Stack>
          ) : null}

          {activeTab === 1 ? (
            <Box sx={{ display: "grid", gap: 3, gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" } }}>
              <Box>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                  <Typography variant="subtitle1" fontWeight="bold">认知插件</Typography>
                  <Chip size="small" label={`${cognitivePlugins.length} 项`} />
                </Stack>
                <SimpleRows items={cognitivePlugins} emptyText="未发现认知插件证据。" />
              </Box>
              <Box>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                  <Typography variant="subtitle1" fontWeight="bold">功能插件</Typography>
                  <Chip size="small" color="secondary" label={`${functionalPlugins.length} 项`} />
                </Stack>
                <SimpleRows items={functionalPlugins} emptyText="未发现功能插件证据。" />
              </Box>
            </Box>
          ) : null}

          {activeTab === 2 ? (
            <Box sx={{ display: "grid", gap: 3, gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" } }}>
              <Box>
                <Typography variant="subtitle1" fontWeight="bold" sx={{ mb: 1 }}>CLI 工具</Typography>
                <SimpleRows items={cliTools} emptyText="未发现 CLI 工具证据。" />
              </Box>
              <Box>
                <Typography variant="subtitle1" fontWeight="bold" sx={{ mb: 1 }}>MCP 工具</Typography>
                <SimpleRows items={mcpServers} emptyText="未发现 MCP 工具证据。" />
              </Box>
              <Box>
                <Typography variant="subtitle1" fontWeight="bold" sx={{ mb: 1 }}>应用连接器</Typography>
                <SimpleRows items={externalConnectors} emptyText="未发现应用连接器证据。" />
              </Box>
              <Box>
                <Typography variant="subtitle1" fontWeight="bold" sx={{ mb: 1 }}>功能执行回执</Typography>
                <SimpleRows items={functionalAssets} emptyText="未发现功能执行回执。" />
              </Box>
            </Box>
          ) : null}

          {activeTab === 3 ? (
            <Box sx={{ display: "grid", gap: 3, gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" } }}>
              <Box>
                <Typography variant="subtitle1" fontWeight="bold" sx={{ mb: 1 }}>外部 Agent</Typography>
                <SimpleRows items={connectedAgents} emptyText="未发现外部 Agent 证据。" />
              </Box>
              <Box>
                <Typography variant="subtitle1" fontWeight="bold" sx={{ mb: 1 }}>长期记忆</Typography>
                <SimpleRows items={memoryItems} emptyText="未发现长期记忆证据。" />
                <Typography variant="subtitle1" fontWeight="bold" sx={{ mt: 3, mb: 1 }}>策略补丁</Typography>
                <SimpleRows items={strategyItems} emptyText="未发现策略补丁证据。" />
              </Box>
            </Box>
          ) : null}

          {activeTab === 4 ? (
            <Stack spacing={1.5}>
              {inference ? (
                <>
                  <Chip
                    label={String(sufficiency.resource_status_label || sufficiency.resource_status || "unknown")}
                    color={sufficiency.resource_status === "sufficient" ? "success" : sufficiency.resource_status === "critically_lacking" ? "error" : "warning"}
                    sx={{ width: "fit-content" }}
                  />
                  <Typography variant="body2">瓶颈节点: {String(sufficiency.bottleneck_node || "none")}</Typography>
                  {missingAssets.length > 0 ? (
                    <Alert severity="warning">
                      <Typography variant="subtitle2">缺失关键资产</Typography>
                      <List dense>
                        {missingAssets.map((item) => (
                          <ListItem key={item}><ListItemText primary={item} /></ListItem>
                        ))}
                      </List>
                    </Alert>
                  ) : null}
                  {sufficiency.reasoning_summary ? (
                    <Typography variant="body2" color="text.secondary">{String(sufficiency.reasoning_summary)}</Typography>
                  ) : null}
                </>
              ) : (
                <Alert severity="info">等待 Q2 资产整理结果。</Alert>
              )}
            </Stack>
          ) : null}
        </CardContent>
      </Card>
    </Stack>
  );
};

export default Q2EvidencePanel;
