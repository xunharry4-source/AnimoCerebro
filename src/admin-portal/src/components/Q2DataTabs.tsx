import { Card, CardContent, Tab, Tabs, Table, TableBody, TableCell, TableContainer, TableRow, Typography } from "@mui/material";
import { useState } from "react";
import { Q2PreprocessedEvidence, Q2WhoAmIInferenceView } from "../pages/nine-questions/nineQuestionsApi";

interface Q2DataTabsProps {
  evidence: Q2PreprocessedEvidence | null;
  inference: Q2WhoAmIInferenceView | null;
}

/**
 * Q2 实际数据Tab面板组件
 */
export default function Q2DataTabs({ evidence, inference }: Q2DataTabsProps) {
  const [activeTab, setActiveTab] = useState(0);
  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => setActiveTab(newValue);

  return (
    <Card variant="outlined" sx={{ mb: 3 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom fontWeight="bold">📊 Q2 实际数据详情</Typography>
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
                  <TableCell>角色推演</TableCell>
                  <TableCell>
                    <Typography variant="body2" color={inference ? "success.main" : "error.main"}>
                      {inference ? `✅ 已推演角色: ${inference.role_profile?.task_role || "N/A"}` : "❌ 未完成"}
                    </Typography>
                  </TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>身份内核装配</TableCell>
                  <TableCell>
                    <Typography variant="body2" color={evidence ? "success.main" : "error.main"}>
                      {evidence ? "✅ 已获取身份内核数据" : "❌ 未获取"}
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
                  <TableCell>Q1 主领域</TableCell>
                  <TableCell><Typography variant="body2">{evidence.q1_summary?.primary_domain || "N/A"}</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>元动机</TableCell>
                  <TableCell><Typography variant="body2">{evidence.identity_kernel?.meta_motivation || "N/A"}</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>价值观禁令</TableCell>
                  <TableCell><Typography variant="body2">{evidence.identity_kernel?.values_prohibition || "N/A"}</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>不可绕过约束</TableCell>
                  <TableCell><Typography variant="body2">{evidence.identity_kernel?.non_bypassable_constraints?.length || 0} 项</Typography></TableCell>
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
                  <TableCell>身份角色</TableCell>
                  <TableCell><Typography variant="body2" fontWeight="bold">{inference.role_profile?.identity_role || "N/A"}</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>活跃角色</TableCell>
                  <TableCell><Typography variant="body2">{inference.role_profile?.active_role || "N/A"}</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>任务角色</TableCell>
                  <TableCell><Typography variant="body2" color="primary">{inference.role_profile?.task_role || "N/A"}</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>当前使命</TableCell>
                  <TableCell><Typography variant="body2">{inference.mission_boundary?.current_mission || "N/A"}</Typography></TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>优先职责</TableCell>
                  <TableCell><Typography variant="body2">{inference.mission_boundary?.priority_duties?.join(", ") || "无"}</Typography></TableCell>
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
