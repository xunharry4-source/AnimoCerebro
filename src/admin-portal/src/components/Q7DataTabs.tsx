import { Card, CardContent, Tab, Tabs, Table, TableBody, TableCell, TableContainer, TableRow, Typography } from "@mui/material";
import { useState } from "react";
import { Q7PreprocessedEvidence, Q7AlternativeStrategyInferenceView } from "../pages/nine-questions/nineQuestionsApi";

interface Q7DataTabsProps {
  evidence: Q7PreprocessedEvidence | null;
  inference: Q7AlternativeStrategyInferenceView | null;
}

export default function Q7DataTabs({ evidence, inference }: Q7DataTabsProps) {
  const [activeTab, setActiveTab] = useState(0);
  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => setActiveTab(newValue);

  return (
    <Card variant="outlined" sx={{ mb: 3 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom fontWeight="bold">📊 Q7 实际数据详情</Typography>
        <Tabs value={activeTab} onChange={handleTabChange} sx={{ mb: 2, borderBottom: 1, borderColor: "divider" }}>
          <Tab label="🎯 目标达成" />
          <Tab label="📊 获取数据" />
          <Tab label="✨ 输出结果" />
        </Tabs>

        {activeTab === 0 && (
          <TableContainer><Table size="small"><TableBody>
            <TableRow sx={{ bgcolor: "action.hover" }}><TableCell sx={{ fontWeight: "bold", width: "40%" }}>目标</TableCell><TableCell sx={{ fontWeight: "bold", width: "60%" }}>达成状态</TableCell></TableRow>
            <TableRow hover><TableCell>备选策略生成</TableCell><TableCell><Typography variant="body2" color={inference ? "success.main" : "error.main"}>{inference ? "✅ 已生成策略" : "❌ 未生成"}</Typography></TableCell></TableRow>
          </TableBody></Table></TableContainer>
        )}

        {activeTab === 1 && evidence && (
          <TableContainer><Table size="small"><TableBody>
            <TableRow sx={{ bgcolor: "action.hover" }}><TableCell sx={{ fontWeight: "bold", width: "30%" }}>数据类型</TableCell><TableCell sx={{ fontWeight: "bold", width: "70%" }}>具体内容</TableCell></TableRow>
            <TableRow hover><TableCell>资源瓶颈</TableCell><TableCell><Typography variant="body2">{evidence.resource_bottlenecks?.length || 0} 项</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>能力限制</TableCell><TableCell><Typography variant="body2">{evidence.capability_limits?.length || 0} 项</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>权限边界</TableCell><TableCell><Typography variant="body2">{evidence.permission_boundaries?.length || 0} 项</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>绝对红线</TableCell><TableCell><Typography variant="body2">{evidence.absolute_red_lines?.length || 0} 项</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>历史失败补丁</TableCell><TableCell><Typography variant="body2">{evidence.historical_failure_patches?.length || 0} 个</Typography></TableCell></TableRow>
          </TableBody></Table></TableContainer>
        )}
        {activeTab === 1 && !evidence && <Typography sx={{ p: 2 }} color="text.secondary">⚠️ 暂无预处理证据数据</Typography>}

        {activeTab === 2 && inference && (
          <TableContainer><Table size="small"><TableBody>
            <TableRow sx={{ bgcolor: "action.hover" }}><TableCell sx={{ fontWeight: "bold", width: "30%" }}>输出字段</TableCell><TableCell sx={{ fontWeight: "bold", width: "70%" }}>值</TableCell></TableRow>
            <TableRow hover><TableCell>回退计划</TableCell><TableCell><Typography variant="body2">{inference.fallback_plans?.length || 0} 项</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>降级策略</TableCell><TableCell><Typography variant="body2">{inference.degradation_strategies?.length || 0} 项</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>协作切换</TableCell><TableCell><Typography variant="body2">{inference.collaboration_switches?.length || 0} 项</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>探索性行动</TableCell><TableCell><Typography variant="body2">{inference.exploratory_actions?.length || 0} 项</Typography></TableCell></TableRow>
          </TableBody></Table></TableContainer>
        )}
        {activeTab === 2 && !inference && <Typography sx={{ p: 2 }} color="text.secondary">⚠️ 暂无推理结果数据</Typography>}
      </CardContent>
    </Card>
  );
}
