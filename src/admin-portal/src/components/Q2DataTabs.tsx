import { Card, CardContent, Tab, Tabs, Table, TableBody, TableCell, TableContainer, TableRow, Typography } from "@mui/material";
import { useState } from "react";
import { Q2PreprocessedEvidence, Q2WhoAmIInferenceView } from "../pages/nine-questions/nineQuestionsApi";

interface Q2DataTabsProps {
  evidence: Q2PreprocessedEvidence | null;
  inference: Q2WhoAmIInferenceView | null;
}

const ASSET_LABELS: Record<string, string> = {
  long_term_memory: "长期记忆",
  cognitive_and_functional_tools: "可用工具",
  connected_agents: "外部 Agent",
  strategy_patches: "策略补丁",
};

function assetSummary(value: unknown): string {
  if (!Array.isArray(value) || value.length === 0) return "0 项";
  const assetNames = value
    .map((rawItem) => {
      const item = rawItem && typeof rawItem === "object" ? (rawItem as Record<string, any>) : {};
      return String(item.asset_name || item.description || item.source || "").trim();
    })
    .filter(Boolean);
  return assetNames.length > 0 ? `${assetNames.length} 项：${assetNames.join(", ")}` : `${value.length} 项`;
}

function hasAssetInventoryData(value: unknown): boolean {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const inventory = value as Record<string, unknown>;
  return Boolean(String(inventory.inventory_summary || "").trim())
    || Object.values(inventory).some((item) => Array.isArray(item) && item.length > 0);
}

export default function Q2DataTabs({ evidence, inference }: Q2DataTabsProps) {
  const [activeTab, setActiveTab] = useState(0);
  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => setActiveTab(newValue);
  const assetInventory = hasAssetInventoryData(inference?.asset_inventory)
    ? inference?.asset_inventory || {}
    : evidence?.asset_inventory || {};
  const assetInventoryReady = hasAssetInventoryData(assetInventory);
  const sufficiency = inference?.sufficiency_assessment as Record<string, any> | undefined;

  return (
    <Card variant="outlined" sx={{ mb: 3 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom fontWeight="bold">Q2 实际数据详情</Typography>
        <Tabs value={activeTab} onChange={handleTabChange} sx={{ mb: 2, borderBottom: 1, borderColor: "divider" }}>
          <Tab label="目标达成" />
          <Tab label="获取数据" />
          <Tab label="输出结果" />
        </Tabs>

        {activeTab === 0 && (
          <TableContainer>
            <Table size="small">
              <TableBody>
                <TableRow sx={{ bgcolor: "action.hover" }}>
                  <TableCell sx={{ fontWeight: "bold", width: "40%" }}>目标</TableCell>
                  <TableCell sx={{ fontWeight: "bold", width: "60%" }}>达成状态</TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>统一资产盘点</TableCell>
                  <TableCell>
                    <Typography variant="body2" color={assetInventoryReady ? "success.main" : "error.main"}>
                      {assetInventoryReady ? "已完成资产盘点" : "未完成"}
                    </Typography>
                  </TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>资源评估</TableCell>
                  <TableCell>
                    <Typography variant="body2" color={sufficiency?.resource_status ? "success.main" : "error.main"}>
                      {sufficiency?.resource_status || "未完成"}
                    </Typography>
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </TableContainer>
        )}

        {activeTab === 1 && evidence && (
          <TableContainer>
            <Table size="small">
              <TableBody>
                <TableRow sx={{ bgcolor: "action.hover" }}>
                  <TableCell sx={{ fontWeight: "bold", width: "30%" }}>数据类型</TableCell>
                  <TableCell sx={{ fontWeight: "bold", width: "70%" }}>具体内容</TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>工具与 Agent 证据</TableCell>
                  <TableCell><Typography variant="body2">{Object.keys(evidence.tools_agents || {}).length} 项</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>记忆与策略证据</TableCell>
                  <TableCell><Typography variant="body2">{Object.keys(evidence.memory_strategy || {}).length} 项</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>AssetInventory 字段数</TableCell>
                  <TableCell><Typography variant="body2">{Object.keys(assetInventory).length} 项</Typography></TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </TableContainer>
        )}
        {activeTab === 1 && !evidence && <Typography sx={{ p: 2 }} color="text.secondary">暂无预处理证据数据</Typography>}

        {activeTab === 2 && inference && (
          <TableContainer>
            <Table size="small">
              <TableBody>
                <TableRow sx={{ bgcolor: "action.hover" }}>
                  <TableCell sx={{ fontWeight: "bold", width: "30%" }}>输出字段</TableCell>
                  <TableCell sx={{ fontWeight: "bold", width: "70%" }}>值</TableCell>
                </TableRow>
                {Object.entries(ASSET_LABELS).map(([key, label]) => (
                  <TableRow hover key={key}>
                    <TableCell>{label}</TableCell>
                    <TableCell><Typography variant="body2">{assetSummary((assetInventory as Record<string, any>)[key])}</Typography></TableCell>
                  </TableRow>
                ))}
                <TableRow hover>
                  <TableCell>Q3 宏观摘要</TableCell>
                  <TableCell><Typography variant="body2">{String((assetInventory as Record<string, any>).inventory_summary || "N/A")}</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>资源状态</TableCell>
                  <TableCell><Typography variant="body2" fontWeight="bold">{sufficiency?.resource_status || "N/A"}</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>缺失关键资产</TableCell>
                  <TableCell><Typography variant="body2">{(sufficiency?.missing_critical_assets || []).join(", ") || "无"}</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>瓶颈节点</TableCell>
                  <TableCell><Typography variant="body2">{sufficiency?.bottleneck_node || "无"}</Typography></TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </TableContainer>
        )}
        {activeTab === 2 && !inference && <Typography sx={{ p: 2 }} color="text.secondary">暂无推理结果数据</Typography>}
      </CardContent>
    </Card>
  );
}
