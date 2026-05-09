import { Card, CardContent, Tab, Tabs, Table, TableBody, TableCell, TableContainer, TableRow, Typography } from "@mui/material";
import { useState } from "react";
import { Q6PreprocessedEvidence, Q6ConsequenceInferenceView } from "../pages/nine-questions/nineQuestionsApi";

interface Q6DataTabsProps {
  evidence: Q6PreprocessedEvidence | null;
  inference: Q6ConsequenceInferenceView | null;
}

export default function Q6DataTabs({ evidence, inference }: Q6DataTabsProps) {
  const [activeTab, setActiveTab] = useState(0);
  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => setActiveTab(newValue);

  return (
    <Card variant="outlined" sx={{ mb: 3 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom fontWeight="bold">Q6 实际数据详情</Typography>
        <Tabs value={activeTab} onChange={handleTabChange} sx={{ mb: 2, borderBottom: 1, borderColor: "divider" }}>
          <Tab label="目标达成" />
          <Tab label="获取数据" />
          <Tab label="输出结果" />
        </Tabs>

        {activeTab === 0 && (
          <TableContainer><Table size="small"><TableBody>
            <TableRow sx={{ bgcolor: "action.hover" }}><TableCell sx={{ fontWeight: "bold", width: "40%" }}>目标</TableCell><TableCell sx={{ fontWeight: "bold", width: "60%" }}>达成状态</TableCell></TableRow>
            <TableRow hover><TableCell>代价与后果评估</TableCell><TableCell><Typography variant="body2" color={inference ? "success.main" : "error.main"}>{inference ? "已完成评估" : "未完成"}</Typography></TableCell></TableRow>
          </TableBody></Table></TableContainer>
        )}

        {activeTab === 1 && evidence && (
          <TableContainer><Table size="small"><TableBody>
            <TableRow sx={{ bgcolor: "action.hover" }}><TableCell sx={{ fontWeight: "bold", width: "30%" }}>数据类型</TableCell><TableCell sx={{ fontWeight: "bold", width: "70%" }}>具体内容</TableCell></TableRow>
            <TableRow hover><TableCell>可行动空间</TableCell><TableCell><Typography variant="body2">{evidence.actionable_space?.length || 0} 项</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>授权边界</TableCell><TableCell><Typography variant="body2">{evidence.authorization_boundaries?.length || 0} 项</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>不可绕过约束</TableCell><TableCell><Typography variant="body2">{evidence.non_bypassable_constraints?.length || 0} 项</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>历史策略补丁</TableCell><TableCell><Typography variant="body2">{evidence.historical_strategy_patches?.length || 0} 个</Typography></TableCell></TableRow>
          </TableBody></Table></TableContainer>
        )}
        {activeTab === 1 && !evidence && <Typography sx={{ p: 2 }} color="text.secondary">⚠️ 暂无预处理证据数据</Typography>}

        {activeTab === 2 && inference && (
          <TableContainer><Table size="small"><TableBody>
            <TableRow sx={{ bgcolor: "action.hover" }}><TableCell sx={{ fontWeight: "bold", width: "30%" }}>输出字段</TableCell><TableCell sx={{ fontWeight: "bold", width: "70%" }}>值</TableCell></TableRow>
            <TableRow hover><TableCell>评估动作</TableCell><TableCell><Typography variant="body2">{inference.ConsequenceAssessment?.action_under_review || "-"}</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>直接后果</TableCell><TableCell><Typography variant="body2" color="warning.main">{inference.ConsequenceAssessment?.immediate_consequences?.length || 0} 项</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>传导后果</TableCell><TableCell><Typography variant="body2">{inference.ConsequenceAssessment?.downstream_consequences?.length || 0} 项</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>严重度</TableCell><TableCell><Typography variant="body2">{inference.ConsequenceAssessment?.consequence_severity || "-"}</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>缓解要求</TableCell><TableCell><Typography variant="body2">{inference.CostImpactProfile?.mitigation_requirements?.length || 0} 项</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>停止条件</TableCell><TableCell><Typography variant="body2">{inference.CostImpactProfile?.stop_conditions?.length || 0} 项</Typography></TableCell></TableRow>
          </TableBody></Table></TableContainer>
        )}
        {activeTab === 2 && !inference && <Typography sx={{ p: 2 }} color="text.secondary">暂无推理结果数据</Typography>}
      </CardContent>
    </Card>
  );
}
