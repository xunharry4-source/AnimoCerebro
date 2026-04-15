import { Card, CardContent, Tab, Tabs, Table, TableBody, TableCell, TableContainer, TableRow, Typography } from "@mui/material";
import { useState } from "react";
import { Q9PreprocessedEvidence, Q9ActionPostureInferenceView } from "../pages/nine-questions/nineQuestionsApi";

interface Q9DataTabsProps {
  evidence: Q9PreprocessedEvidence | null;
  inference: Q9ActionPostureInferenceView | null;
}

export default function Q9DataTabs({ evidence, inference }: Q9DataTabsProps) {
  const [activeTab, setActiveTab] = useState(0);
  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => setActiveTab(newValue);

  return (
    <Card variant="outlined" sx={{ mb: 3 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom fontWeight="bold">📊 Q9 实际数据详情</Typography>
        <Tabs value={activeTab} onChange={handleTabChange} sx={{ mb: 2, borderBottom: 1, borderColor: "divider" }}>
          <Tab label="🎯 目标达成" />
          <Tab label="📊 获取数据" />
          <Tab label="✨ 输出结果" />
        </Tabs>

        {activeTab === 0 && (
          <TableContainer><Table size="small"><TableBody>
            <TableRow sx={{ bgcolor: "action.hover" }}><TableCell sx={{ fontWeight: "bold", width: "40%" }}>目标</TableCell><TableCell sx={{ fontWeight: "bold", width: "60%" }}>达成状态</TableCell></TableRow>
            <TableRow hover><TableCell>行动姿态定调</TableCell><TableCell><Typography variant="body2" color={inference ? "success.main" : "error.main"}>{inference ? "✅ 已定调姿态" : "❌ 未定调"}</Typography></TableCell></TableRow>
          </TableBody></Table></TableContainer>
        )}

        {activeTab === 1 && evidence && (
          <TableContainer><Table size="small"><TableBody>
            <TableRow sx={{ bgcolor: "action.hover" }}><TableCell sx={{ fontWeight: "bold", width: "30%" }}>数据类型</TableCell><TableCell sx={{ fontWeight: "bold", width: "70%" }}>具体内容</TableCell></TableRow>
            <TableRow hover><TableCell>Q1-Q8认知快照</TableCell><TableCell><Typography variant="body2">{Object.keys(evidence.cognitive_snapshot?.q1_to_q8_snapshot || {}).length} 个字段</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>不确定性数</TableCell><TableCell><Typography variant="body2">{evidence.cognitive_snapshot?.uncertainty_count || 0} 项</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>绝对红线数</TableCell><TableCell><Typography variant="body2">{evidence.cognitive_snapshot?.absolute_red_line_count || 0} 项</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>认知负载</TableCell><TableCell><Typography variant="body2">{evidence.self_model?.cognitive_load || "N/A"}</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>稳定性级别</TableCell><TableCell><Typography variant="body2">{evidence.self_model?.stability_level || "N/A"}</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>置信度漂移</TableCell><TableCell><Typography variant="body2">{evidence.self_model?.confidence_drift != null ? (evidence.self_model.confidence_drift * 100).toFixed(1) + "%" : "N/A"}</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>近期弱点</TableCell><TableCell><Typography variant="body2">{evidence.self_model?.recent_weaknesses?.length || 0} 项</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>计算剩余比例</TableCell><TableCell><Typography variant="body2">{((evidence.reasoning_budget?.compute_remaining_ratio || 0) * 100).toFixed(1)}%</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>Token剩余比例</TableCell><TableCell><Typography variant="body2">{((evidence.reasoning_budget?.token_remaining_ratio || 0) * 100).toFixed(1)}%</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>时间剩余比例</TableCell><TableCell><Typography variant="body2">{((evidence.reasoning_budget?.time_remaining_ratio || 0) * 100).toFixed(1)}%</Typography></TableCell></TableRow>
          </TableBody></Table></TableContainer>
        )}
        {activeTab === 1 && !evidence && <Typography sx={{ p: 2 }} color="text.secondary">⚠️ 暂无预处理证据数据</Typography>}

        {activeTab === 2 && inference && (
          <TableContainer><Table size="small"><TableBody>
            <TableRow sx={{ bgcolor: "action.hover" }}><TableCell sx={{ fontWeight: "bold", width: "30%" }}>输出字段</TableCell><TableCell sx={{ fontWeight: "bold", width: "70%" }}>值</TableCell></TableRow>
            <TableRow hover><TableCell>评估风格</TableCell><TableCell><Typography variant="body2" fontWeight="bold">{inference.evaluation_style || "N/A"}</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>风险容忍度</TableCell><TableCell><Typography variant="body2">{inference.risk_tolerance || "N/A"}</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>行动节奏</TableCell><TableCell><Typography variant="body2">{inference.action_rhythm || "N/A"}</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>确认策略</TableCell><TableCell><Typography variant="body2">{inference.confirmation_strategy || "N/A"}</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>进化方向</TableCell><TableCell><Typography variant="body2" color="info.main">{inference.evolution_direction || "N/A"}</Typography></TableCell></TableRow>
          </TableBody></Table></TableContainer>
        )}
        {activeTab === 2 && !inference && <Typography sx={{ p: 2 }} color="text.secondary">⚠️ 暂无推理结果数据</Typography>}
      </CardContent>
    </Card>
  );
}
