import { Box, Card, CardContent, Tab, Tabs, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import { Q8PreprocessedEvidence, Q8WhatShouldIDoNowInferenceView } from "../pages/nine-questions/nineQuestionsApi";

interface Q8DataTabsProps {
  evidence: Q8PreprocessedEvidence | null;
  inference: Q8WhatShouldIDoNowInferenceView | null;
}

export default function Q8DataTabs({ evidence, inference }: Q8DataTabsProps) {
  const [activeTab, setActiveTab] = useState(() => (evidence ? 1 : 0));
  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => setActiveTab(newValue);

  const KeyValueRows = ({ rows }: { rows: Array<{ label: string; value: string }> }) => (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: { xs: "1fr", sm: "minmax(180px, 240px) 1fr" },
        borderTop: 1,
        borderLeft: 1,
        borderColor: "divider",
      }}
    >
      {rows.flatMap((row) => ([
        <Box
          key={`${row.label}-label`}
          sx={{
            px: 2,
            py: 1.5,
            bgcolor: "action.hover",
            borderRight: 1,
            borderBottom: 1,
            borderColor: "divider",
            color: "text.primary",
            fontWeight: 600,
          }}
        >
          {row.label}
        </Box>,
        <Box
          key={`${row.label}-value`}
          sx={{
            px: 2,
            py: 1.5,
            borderBottom: 1,
            borderColor: "divider",
            color: "text.primary",
            WebkitTextFillColor: (theme) => theme.palette.text.primary,
            wordBreak: "break-word",
          }}
        >
          {row.value}
        </Box>,
      ]))}
    </Box>
  );

  useEffect(() => {
    if (evidence) {
      setActiveTab(1);
      return;
    }
    setActiveTab(0);
  }, [evidence, inference]);

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
          <KeyValueRows
            rows={[
              {
                label: "目标",
                value: "任务优先级与目标生成",
              },
              {
                label: "达成状态",
                value: inference ? "已生成目标" : "未生成",
              },
            ]}
          />
        )}

        {activeTab === 1 && evidence && (
          <KeyValueRows
            rows={[
              {
                label: "Q1-Q7聚合上下文",
                value: `${Object.keys(evidence.aggregated_context?.q1_to_q7_snapshot || {}).length} 个字段`,
              },
              {
                label: "绝对红线数",
                value: `${evidence.aggregated_context?.absolute_red_line_count || 0} 项`,
              },
              {
                label: "能力上限数",
                value: `${evidence.aggregated_context?.capability_ceiling_count || 0} 项`,
              },
              {
                label: "持久化任务数",
                value: `${evidence.runtime_state?.persistent_task_state?.length || 0} 个`,
              },
              {
                label: "认知议程数",
                value: `${evidence.runtime_state?.cognitive_agenda?.length || 0} 个`,
              },
            ]}
          />
        )}
        {activeTab === 1 && !evidence && <Typography sx={{ p: 2 }} color="text.secondary">⚠️ 暂无预处理证据数据</Typography>}

        {activeTab === 2 && inference && (
          <KeyValueRows
            rows={[
              {
                label: "当前主目标",
                value: inference.objective_profile?.current_primary_objective || "N/A",
              },
              {
                label: "阶段任务数",
                value: `${inference.objective_profile?.current_phase_tasks?.length || 0} 项`,
              },
              {
                label: "优先级顺序",
                value: inference.objective_profile?.priority_order?.join(" → ") || "N/A",
              },
              {
                label: "下一步自主任务",
                value: `${inference.task_queue?.next_self_tasks?.length || 0} 个`,
              },
              {
                label: "阻塞任务",
                value: `${inference.task_queue?.blocked_self_tasks?.length || 0} 个`,
              },
              {
                label: "主动行动",
                value: `${inference.task_queue?.proactive_actions?.length || 0} 个`,
              },
            ]}
          />
        )}
        {activeTab === 2 && !inference && <Typography sx={{ p: 2 }} color="text.secondary">⚠️ 暂无推理结果数据</Typography>}
      </CardContent>
    </Card>
  );
}
