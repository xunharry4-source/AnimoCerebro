import { Card, CardContent, Tab, Tabs, Table, TableBody, TableCell, TableContainer, TableRow, Typography } from "@mui/material";
import { useState } from "react";
import { Q8PreprocessedEvidence, Q8WhatShouldIDoNowInferenceView } from "../pages/nine-questions/nineQuestionsApi";

interface Q8DataTabsProps {
  evidence: Q8PreprocessedEvidence | null;
  inference: Q8WhatShouldIDoNowInferenceView | null;
}

export default function Q8DataTabs({ evidence, inference }: Q8DataTabsProps) {
  const [activeTab, setActiveTab] = useState(0);
  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => setActiveTab(newValue);

  return (
    <Card variant="outlined" sx={{ mb: 3 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom fontWeight="bold">📊 Q8 实际数据详情</Typography>
        <Tabs value={activeTab} onChange={handleTabChange} sx={{ mb: 2, borderBottom: 1, borderColor: "divider" }}>
          <Tab label="🎯 目标达成" />
          <Tab label="📊 获取数据" />
          <Tab label="✨ 输出结果" />
        </Tabs>

        {activeTab === 0 && (
          <TableContainer><Table size="small"><TableBody>
            <TableRow sx={{ bgcolor: "action.hover" }}><TableCell sx={{ fontWeight: "bold", width: "40%" }}>目标</TableCell><TableCell sx={{ fontWeight: "bold", width: "60%" }}>达成状态</TableCell></TableRow>
            <TableRow hover><TableCell>任务优先级与目标生成</TableCell><TableCell><Typography variant="body2" color={inference ? "success.main" : "error.main"}>{inference ? "✅ 已生成目标" : "❌ 未生成"}</Typography></TableCell></TableRow>
          </TableBody></Table></TableContainer>
        )}

        {activeTab === 1 && evidence && (
          <TableContainer><Table size="small"><TableBody>
            <TableRow sx={{ bgcolor: "action.hover" }}><TableCell sx={{ fontWeight: "bold", width: "30%" }}>数据类型</TableCell><TableCell sx={{ fontWeight: "bold", width: "70%" }}>具体内容</TableCell></TableRow>
            <TableRow hover><TableCell>Q1-Q7聚合上下文</TableCell><TableCell><Typography variant="body2">{Object.keys(evidence.aggregated_context?.q1_to_q7_snapshot || {}).length} 个字段</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>绝对红线数</TableCell><TableCell><Typography variant="body2">{evidence.aggregated_context?.absolute_red_line_count || 0} 项</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>能力上限数</TableCell><TableCell><Typography variant="body2">{evidence.aggregated_context?.capability_ceiling_count || 0} 项</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>持久化任务数</TableCell><TableCell><Typography variant="body2">{evidence.runtime_state?.persistent_task_state?.length || 0} 个</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>认知议程数</TableCell><TableCell><Typography variant="body2">{evidence.runtime_state?.cognitive_agenda?.length || 0} 个</Typography></TableCell></TableRow>
          </TableBody></Table></TableContainer>
        )}
        {activeTab === 1 && !evidence && <Typography sx={{ p: 2 }} color="text.secondary">⚠️ 暂无预处理证据数据</Typography>}

        {activeTab === 2 && inference && (
          <TableContainer><Table size="small"><TableBody>
            <TableRow sx={{ bgcolor: "action.hover" }}><TableCell sx={{ fontWeight: "bold", width: "30%" }}>输出字段</TableCell><TableCell sx={{ fontWeight: "bold", width: "70%" }}>值</TableCell></TableRow>
            <TableRow hover><TableCell>当前主目标</TableCell><TableCell><Typography variant="body2" fontWeight="bold" color="primary">{inference.objective_profile?.current_primary_objective || "N/A"}</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>阶段任务数</TableCell><TableCell><Typography variant="body2">{inference.objective_profile?.current_phase_tasks?.length || 0} 项</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>优先级顺序</TableCell><TableCell><Typography variant="body2">{inference.objective_profile?.priority_order?.join(" → ") || "N/A"}</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>下一步自主任务</TableCell><TableCell><Typography variant="body2">{inference.task_queue?.next_self_tasks?.length || 0} 个</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>阻塞任务</TableCell><TableCell><Typography variant="body2">{inference.task_queue?.blocked_self_tasks?.length || 0} 个</Typography></TableCell></TableRow>
            <TableRow hover><TableCell>主动行动</TableCell><TableCell><Typography variant="body2">{inference.task_queue?.proactive_actions?.length || 0} 个</Typography></TableCell></TableRow>
          </TableBody></Table></TableContainer>
        )}
        {activeTab === 2 && !inference && <Typography sx={{ p: 2 }} color="text.secondary">⚠️ 暂无推理结果数据</Typography>}
      </CardContent>
    </Card>
  );
}
