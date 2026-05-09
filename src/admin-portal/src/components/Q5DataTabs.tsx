import { Card, CardContent, Tab, Tabs, Table, TableBody, TableCell, TableContainer, TableRow, Typography } from "@mui/material";
import { useState } from "react";
import { Q5PreprocessedEvidence, Q5WhatAmIAllowedToDoInferenceView } from "../pages/nine-questions/nineQuestionsApi";

interface Q5DataTabsProps {
  evidence: Q5PreprocessedEvidence | null;
  inference: Q5WhatAmIAllowedToDoInferenceView | null;
}

export default function Q5DataTabs({ evidence, inference }: Q5DataTabsProps) {
  const [activeTab, setActiveTab] = useState(0);
  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => setActiveTab(newValue);

  return (
    <Card variant="outlined" sx={{ mb: 3 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom fontWeight="bold">Q5 实际数据详情</Typography>
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
                  <TableCell>禁止边界判断</TableCell>
                  <TableCell><Typography variant="body2" color={inference ? "success.main" : "error.main"}>{inference ? "已完成判断" : "未完成"}</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>合规性检查</TableCell>
                  <TableCell><Typography variant="body2" color={evidence ? "success.main" : "error.main"}>{evidence ? "已完成检查" : "未完成"}</Typography></TableCell>
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
                <TableRow hover><TableCell>可行动空间</TableCell><TableCell><Typography variant="body2">{evidence.actionable_space?.length || 0} 项</Typography></TableCell></TableRow>
                <TableRow hover><TableCell>联系策略</TableCell><TableCell><Typography variant="body2">{evidence.contact_policy?.length || 0} 项</Typography></TableCell></TableRow>
                <TableRow hover><TableCell>租户边界</TableCell><TableCell><Typography variant="body2">{evidence.tenant_boundaries?.length || 0} 项</Typography></TableCell></TableRow>
                <TableRow hover><TableCell>Agent信任状态</TableCell><TableCell><Typography variant="body2">{Object.keys(evidence.agent_trust_status || {}).length} 个</Typography></TableCell></TableRow>
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
                <TableRow hover><TableCell>执行层级</TableCell><TableCell><Typography variant="body2" fontWeight="bold">{inference.execution_tier || "N/A"}</Typography></TableCell></TableRow>
                <TableRow hover><TableCell>交互范围</TableCell><TableCell><Typography variant="body2">{inference.interaction_scope || "N/A"}</Typography></TableCell></TableRow>
                <TableRow hover><TableCell>需人工确认</TableCell><TableCell><Typography variant="body2">{inference.requires_human_confirmation ? "是" : "否"}</Typography></TableCell></TableRow>
                <TableRow hover><TableCell>需云审计</TableCell><TableCell><Typography variant="body2">{inference.requires_cloud_audit ? "是" : "否"}</Typography></TableCell></TableRow>
                <TableRow hover><TableCell>明确禁止操作</TableCell><TableCell><Typography variant="body2">{inference.explicitly_forbidden_actions?.length || 0} 项</Typography></TableCell></TableRow>
                <TableRow hover><TableCell>合规风险</TableCell><TableCell><Typography variant="body2">{inference.compliance_risks?.length || 0} 项</Typography></TableCell></TableRow>
              </TableBody>
            </Table>
          </TableContainer>
        )}
        {activeTab === 2 && !inference && <Typography sx={{ p: 2 }} color="text.secondary">⚠️ 暂无推理结果数据</Typography>}
      </CardContent>
    </Card>
  );
}
