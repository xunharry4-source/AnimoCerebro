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
  const role = inference?.role_profile;
  const mission = inference?.mission_boundary;

  return (
    <Card variant="outlined" sx={{ mb: 3 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom fontWeight="bold">Q3 实际数据详情</Typography>
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
                  <TableCell>角色推断</TableCell>
                  <TableCell>
                    <Typography variant="body2" color={role ? "success.main" : "error.main"}>
                      {role ? `已推断角色: ${role.task_role || role.active_role || "N/A"}` : "未完成"}
                    </Typography>
                  </TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>Q1/Q2 前置依赖</TableCell>
                  <TableCell>
                    <Typography variant="body2" color={evidence?.q2_asset_inventory ? "success.main" : "error.main"}>
                      {evidence?.q2_asset_inventory ? "已读取 Q1 环境和 Q2 资产" : "未获取完整前置数据"}
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
                  <TableCell>Q1 环境推断</TableCell>
                  <TableCell><Typography variant="body2">{Object.keys(evidence.q1_environment_inference || {}).length} 项</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>Q2 资产盘点</TableCell>
                  <TableCell><Typography variant="body2">{Object.keys(evidence.q2_asset_inventory || {}).length} 项</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>身份内核</TableCell>
                  <TableCell><Typography variant="body2">{Object.keys(evidence.identity_kernel_snapshot || {}).length} 项</Typography></TableCell>
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
                <TableRow hover>
                  <TableCell>身份角色</TableCell>
                  <TableCell><Typography variant="body2" fontWeight="bold">{role?.identity_role || "N/A"}</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>活跃角色</TableCell>
                  <TableCell><Typography variant="body2">{role?.active_role || "N/A"}</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>系统推断参考角色</TableCell>
                  <TableCell><Typography variant="body2">{role?.inferred_reference_role || "N/A"}</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>角色适配度偏差</TableCell>
                  <TableCell><Typography variant="body2">{role?.role_alignment_gap || "N/A"}</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>当前使命</TableCell>
                  <TableCell><Typography variant="body2">{mission?.current_mission || "N/A"}</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>优先职责</TableCell>
                  <TableCell><Typography variant="body2">{mission?.priority_duties?.join(", ") || "无"}</Typography></TableCell>
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
