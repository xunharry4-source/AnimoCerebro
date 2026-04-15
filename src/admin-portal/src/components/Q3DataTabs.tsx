import { Card, CardContent, Tab, Tabs, Table, TableBody, TableCell, TableContainer, TableRow, Typography } from "@mui/material";
import { useState } from "react";
import { Q3PreprocessedEvidence, Q3WhatDoIHaveInferenceView } from "../pages/nine-questions/nineQuestionsApi";

interface Q3DataTabsProps {
  evidence: Q3PreprocessedEvidence | null;
  inference: Q3WhatDoIHaveInferenceView | null;
}

export default function Q3DataTabs({ evidence, inference }: Q3DataTabsProps) {
  const [activeTab, setActiveTab] = useState(0);
  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => setActiveTab(newValue);

  return (
    <Card variant="outlined" sx={{ mb: 3 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom fontWeight="bold">📊 Q3 实际数据详情</Typography>
        <Tabs value={activeTab} onChange={handleTabChange} sx={{ mb: 2, borderBottom: 1, borderColor: "divider" }}>
          <Tab label="🎯 目标达成" />
          <Tab label="📊 获取数据" />
          <Tab label="✨ 输出结果" />
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
                    <Typography variant="body2" color={evidence ? "success.main" : "error.main"}>
                      {evidence ? "✅ 已完成资产盘点" : "❌ 未完成"}
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
                  <TableCell>工作区数</TableCell>
                  <TableCell><Typography variant="body2">{evidence.workspace_permission?.workspaces?.length || 0} 个</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>认知工具数</TableCell>
                  <TableCell><Typography variant="body2">{evidence.tools_agents?.cognitive_tools?.length || 0} 个</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>执行工具数</TableCell>
                  <TableCell><Typography variant="body2">{evidence.tools_agents?.execution_tools?.length || 0} 个</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>已连接Agent数</TableCell>
                  <TableCell><Typography variant="body2">{evidence.tools_agents?.connected_agents?.length || 0} 个</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>MCP服务器数</TableCell>
                  <TableCell><Typography variant="body2">{evidence.tools_agents?.mcp_servers?.length || 0} 个</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>CLI工具数</TableCell>
                  <TableCell><Typography variant="body2">{evidence.tools_agents?.cli_tools?.length || 0} 个</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>经验日志数</TableCell>
                  <TableCell><Typography variant="body2">{evidence.memory_strategy?.experience_logs?.length || 0} 条</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>策略补丁数</TableCell>
                  <TableCell><Typography variant="body2">{evidence.memory_strategy?.strategy_patches?.length || 0} 个</Typography></TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </TableContainer>
        )}
        {activeTab === 1 && !evidence && <Typography sx={{ p: 2 }} color="text.secondary">⚠️ 暂无预处理证据数据</Typography>}

        {activeTab === 2 && inference && (
          <TableContainer>
            <Table size="small">
              <TableBody>
                <TableRow sx={{ bgcolor: "action.hover" }}>
                  <TableCell sx={{ fontWeight: "bold", width: "30%" }}>输出字段</TableCell>
                  <TableCell sx={{ fontWeight: "bold", width: "70%" }}>值</TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>资源状态</TableCell>
                  <TableCell><Typography variant="body2" fontWeight="bold">{inference.sufficiency_assessment?.resource_status || "N/A"}</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>缺失关键资产</TableCell>
                  <TableCell><Typography variant="body2">{inference.sufficiency_assessment?.missing_critical_assets?.length || 0} 项</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>瓶颈节点</TableCell>
                  <TableCell><Typography variant="body2">{inference.sufficiency_assessment?.bottleneck_node || "无"}</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>推理摘要</TableCell>
                  <TableCell><Typography variant="body2" sx={{ fontSize: "0.85rem" }}>{inference.sufficiency_assessment?.reasoning_summary || "N/A"}</Typography></TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </TableContainer>
        )}
        {activeTab === 2 && !inference && <Typography sx={{ p: 2 }} color="text.secondary">⚠️ 暂无推理结果数据</Typography>}
      </CardContent>
    </Card>
  );
}
