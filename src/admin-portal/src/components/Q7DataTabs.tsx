import { Card, CardContent, Tab, Tabs, Table, TableBody, TableCell, TableContainer, TableRow, Typography } from "@mui/material";
import { useState } from "react";
import { Q7PreprocessedEvidence, Q7AlternativeStrategyInferenceView } from "../pages/nine-questions/nineQuestionsApi";

interface Q7DataTabsProps {
  evidence: Q7PreprocessedEvidence | null;
  inference: Q7AlternativeStrategyInferenceView | null;
}

const fieldMeanings: Array<[keyof Q7AlternativeStrategyInferenceView, string]> = [
  ["current_red_line_hits", "当前运行状态或待办中已经触碰、即将触碰的红线警告；无命中也必须明确说明。"],
  ["rejected_operation_records", "近期被 SafetyGate、云审计或同等安全模块正式拒绝的高危操作历史。"],
  ["ban_source_explanations", "解释当前生效禁令分别来自身份内核、Q5、安全审计、程序记忆或其他来源。"],
  ["non_bypassable_constraints", "保障主体连续性与绝对安全的不可绕过底线，Q8 不能用效率或探索目标覆盖。"],
  ["question_driver_refs", "推断以上红线引用的前置 Q5、身份内核、安全日志或程序记忆来源。"],
];

export default function Q7DataTabs({ evidence, inference }: Q7DataTabsProps) {
  const [activeTab, setActiveTab] = useState(0);
  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => setActiveTab(newValue);

  return (
    <Card variant="outlined" sx={{ mb: 3, borderColor: "error.main" }}>
      <CardContent>
        <Typography variant="h6" gutterBottom fontWeight="bold">Q7 红线评估数据详情</Typography>
        <Tabs value={activeTab} onChange={handleTabChange} sx={{ mb: 2, borderBottom: 1, borderColor: "divider" }}>
          <Tab label="字段含义" />
          <Tab label="输入证据" />
          <Tab label="LLM 输出" />
        </Tabs>

        {activeTab === 0 && (
          <TableContainer><Table size="small"><TableBody>
            <TableRow sx={{ bgcolor: "action.hover" }}><TableCell sx={{ fontWeight: "bold", width: "30%" }}>字段</TableCell><TableCell sx={{ fontWeight: "bold", width: "70%" }}>含义</TableCell></TableRow>
            {fieldMeanings.map(([field, meaning]) => (
              <TableRow hover key={field}><TableCell sx={{ fontFamily: "monospace" }}>{field}</TableCell><TableCell><Typography variant="body2">{meaning}</Typography></TableCell></TableRow>
            ))}
          </TableBody></Table></TableContainer>
        )}

        {activeTab === 1 && evidence && (
          <TableContainer><Table size="small"><TableBody>
            <TableRow sx={{ bgcolor: "action.hover" }}><TableCell sx={{ fontWeight: "bold", width: "30%" }}>证据类型</TableCell><TableCell sx={{ fontWeight: "bold", width: "70%" }}>数量</TableCell></TableRow>
            <TableRow hover><TableCell>身份内核底线</TableCell><TableCell>{evidence.identity_kernel_constraints?.length || 0} 项</TableCell></TableRow>
            <TableRow hover><TableCell>授权边界约束</TableCell><TableCell>{evidence.authorization_boundary_constraints?.length || 0} 项</TableCell></TableRow>
            <TableRow hover><TableCell>安全拒绝记录</TableCell><TableCell>{evidence.safety_rejection_history?.length || 0} 项</TableCell></TableRow>
            <TableRow hover><TableCell>程序记忆禁令</TableCell><TableCell>{evidence.procedural_memory_constraints?.length || 0} 项</TableCell></TableRow>
            <TableRow hover><TableCell>不可绕过约束</TableCell><TableCell>{evidence.non_bypassable_constraints?.length || 0} 项</TableCell></TableRow>
            <TableRow hover><TableCell>禁令来源说明</TableCell><TableCell>{evidence.ban_source_explanations?.length || 0} 项</TableCell></TableRow>
            <TableRow hover><TableCell>引用来源</TableCell><TableCell>{evidence.question_driver_refs?.length || 0} 项</TableCell></TableRow>
          </TableBody></Table></TableContainer>
        )}
        {activeTab === 1 && !evidence && <Typography sx={{ p: 2 }} color="text.secondary">暂无预处理证据数据</Typography>}

        {activeTab === 2 && inference && (
          <TableContainer><Table size="small"><TableBody>
            <TableRow sx={{ bgcolor: "action.hover" }}><TableCell sx={{ fontWeight: "bold", width: "30%" }}>输出字段</TableCell><TableCell sx={{ fontWeight: "bold", width: "70%" }}>数量</TableCell></TableRow>
            {fieldMeanings.map(([field]) => (
              <TableRow hover key={field}><TableCell sx={{ fontFamily: "monospace" }}>{field}</TableCell><TableCell>{inference[field]?.length || 0} 项</TableCell></TableRow>
            ))}
          </TableBody></Table></TableContainer>
        )}
        {activeTab === 2 && !inference && <Typography sx={{ p: 2 }} color="text.secondary">暂无推理结果数据</Typography>}
      </CardContent>
    </Card>
  );
}
