import { Card, CardContent, Tab, Tabs, Table, TableBody, TableCell, TableContainer, TableRow, Typography } from "@mui/material";
import { useState } from "react";
import { Q4PreprocessedEvidence, Q4WhatCanIDoInferenceView } from "../pages/nine-questions/nineQuestionsApi";

interface Q4DataTabsProps {
  evidence: Q4PreprocessedEvidence | null;
  inference: Q4WhatCanIDoInferenceView | null;
}

export default function Q4DataTabs({ evidence, inference }: Q4DataTabsProps) {
  const [activeTab, setActiveTab] = useState(0);
  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => setActiveTab(newValue);

  return (
    <Card variant="outlined" sx={{ mb: 3 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom fontWeight="bold">📊 Q4 实际数据详情</Typography>
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
                  <TableCell>能力边界评估</TableCell>
                  <TableCell>
                    <Typography variant="body2" color={inference ? "success.main" : "error.main"}>
                      {inference ? "✅ 已完成能力评估" : "❌ 未完成"}
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
                  <TableCell>Q1 上下文</TableCell>
                  <TableCell><Typography variant="body2">{Object.keys(evidence.q1_context || {}).length} 个字段</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>Q2 上下文</TableCell>
                  <TableCell><Typography variant="body2">{Object.keys(evidence.q2_context || {}).length} 个字段</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>Q3 资产清单</TableCell>
                  <TableCell><Typography variant="body2">{Object.keys(evidence.q3_inventory || {}).length} 个字段</Typography></TableCell>
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
                  <TableCell>能力上限</TableCell>
                  <TableCell><Typography variant="body2">{inference.capability_upper_limits?.length || 0} 项</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>可行动空间</TableCell>
                  <TableCell><Typography variant="body2">{inference.actionable_space?.length || 0} 项</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>可执行策略</TableCell>
                  <TableCell><Typography variant="body2">{inference.executable_strategies?.length || 0} 项</Typography></TableCell>
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
