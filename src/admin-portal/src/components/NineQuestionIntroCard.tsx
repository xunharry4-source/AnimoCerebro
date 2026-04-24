import { Box, Card, CardContent, Stack, Typography } from "@mui/material";

/**
 * 九问介绍信息定义
 */
interface QuestionIntroInfo {
  title: string;
  goals: string[];
  expectedData: string[];
  outputs: string[];
}

/**
 * 九问介绍数据（基于 Zentex 产品功能文档）
 */
const NINE_QUESTIONS_INTRO: Record<string, QuestionIntroInfo> = {
  q1: {
    title: "我在哪",
    goals: [
      "环境态势感知 + 工作区领域归类",
      "识别当前所处的物理和逻辑环境",
    ],
    expectedData: [
      "物理主机状态（PhysicalHostState）",
      "工作区结构分析（WorkspaceStructureAnalyzer）",
      "内容采样摘要（WorkspaceContentSampler）",
      "不确定性提示",
    ],
    outputs: [
      "主领域（primary_domain）",
      "次领域列表（secondary_domains）",
      "置信度（confidence）",
      "推理摘要（reasoning_summary）",
      "不确定性列表（uncertainties）",
      "建议第一步（suggested_first_step）",
    ],
  },
  q2: {
    title: "我是谁",
    goals: [
      "角色推演 + 身份内核装配",
      "基于 Q1 的环境态势和底层身份约束推断当前最适合的任务角色",
    ],
    expectedData: [
      "Q1 态势结果（环境领域推断）",
      "身份内核（元动机/禁令/不可绕过约束）",
      "主观风险偏好权重",
      "人工干预回执（如有）",
    ],
    outputs: [
      "角色画像：身份角色（identity_role）",
      "角色画像：活跃角色（active_role）",
      "角色画像：任务角色（task_role）",
      "使命连续性边界：当前使命（current_mission）",
      "使命连续性边界：优先职责（priority_duties）",
      "使命连续性边界：连续性边界（continuity_boundaries）",
    ],
  },
  q3: {
    title: "我有什么",
    goals: [
      "统一资产盘点",
      "全面梳理当前可用的认知工具、执行域、Agent、策略补丁和工作区权限",
    ],
    expectedData: [
      "认知工具注册表（cognitive_tool_registry）",
      "执行域目录（execution_domain_registry）",
      "已连接 Agent 列表（connected_agents）",
      "激活的策略补丁（activated_strategy_patches）",
      "可访问工作区区域（accessible_workspace_zones）",
    ],
    outputs: [
      "统一资产清单（unified_asset_inventory）",
      "资源评估：资源状态（resource_status）",
      "资源评估：缺失关键资产（missing_critical_assets）",
      "资源评估：瓶颈节点（bottleneck_node）",
      "资源评估：推理摘要（reasoning_summary）",
    ],
  },
  q4: {
    title: "我能做什么",
    goals: [
      "能力边界评估",
      "基于 Q3 的资产清单和当前权限，评估系统真正具备的行动能力",
      "严格禁止幻觉声明不存在的能力",
    ],
    expectedData: [
      "Q3 资产清单（unified_asset_inventory）",
      "活跃执行域（active_execution_domains）",
      "权限边界（permissions）",
      "Q1-Q2 的前置态势",
    ],
    outputs: [
      "能力上限（capability_upper_limits）",
      "可行动空间（actionable_space）",
      "可执行策略（executable_strategies）",
    ],
  },
  q5: {
    title: "我被允许做什么",
    goals: [
      "授权边界判断 + 合规性检查",
      "在 Q4 的能力范围内进一步筛选出被授权允许执行的操作",
    ],
    expectedData: [
      "Q4 能力边界（capability_boundary_profile）",
      "联系策略（contact_policy）",
      "租户范围（tenant_scope）",
      "Agent 信任策略（agent_trust_policy）",
      "组织边界规则",
    ],
    outputs: [
      "允许操作空间（allowed_action_space）",
      "禁止操作空间及原因（forbidden_action_space）",
      "联系和组织边界（contact_and_org_boundaries）",
      "需要升级的操作（requires_escalation_actions）",
    ],
  },
  q6: {
    title: "我即使能做也不该做什么",
    goals: [
      "红线和禁区检查",
      "识别绝对不可触碰的安全边界和性能权衡禁令",
    ],
    expectedData: [
      "可行动空间（actionable_space）",
      "授权边界（authorization_boundaries）",
      "不可绕过约束（non_bypassable_constraints）",
      "历史策略补丁（historical_strategy_patches）",
      "安全红线规则",
    ],
    outputs: [
      "绝对红线（absolute_red_lines）",
      "性能权衡禁令（performance_tradeoff_bans）",
      "禁止策略（prohibited_strategies）",
      "污染风险（contamination_risks）",
    ],
  },
  q7: {
    title: "我还可以做什么",
    goals: [
      "备选策略生成",
      "当主路径受阻时提供降级方案、协作切换和探索性行动建议",
    ],
    expectedData: [
      "资源瓶颈（resource_bottlenecks）",
      "能力限制（capability_limits）",
      "权限边界（permission_boundaries）",
      "绝对红线（absolute_red_lines）",
      "历史失败补丁（historical_failure_patches）",
    ],
    outputs: [
      "回退计划（fallback_plans）",
      "降级策略（degradation_strategies）",
      "协作切换方案（collaboration_switches）",
      "探索性行动（exploratory_actions）",
    ],
  },
  q8: {
    title: "我现在应该做什么",
    goals: [
      "任务优先级与目标生成",
      "汇总 Q1-Q7 的约束与能力，生成当前最优主目标和任务队列",
    ],
    expectedData: [
      "Q1-Q7 聚合上下文（q1_to_q7_snapshot）",
      "绝对红线数量（absolute_red_line_count）",
      "能力天花板计数（capability_ceiling_count）",
      "持久化任务状态（persistent_tasks）",
    ],
    outputs: [
      "目标画像：当前主目标（current_primary_objective）",
      "目标画像：阶段任务（current_phase_tasks）",
      "目标画像：优先级排序（priority_order）",
      "自主任务队列：下一步任务（next_self_tasks）",
      "自主任务队列：阻塞任务（blocked_self_tasks）",
      "自主任务队列：主动行动（proactive_actions）",
    ],
  },
  q9: {
    title: "我应该如何行动",
    goals: [
      "行动姿态定调",
      "根据 Q1-Q8 的状态确定行动风格、节奏和确认策略",
    ],
    expectedData: [
      "Q1-Q8 认知快照（q1_to_q8_snapshot）",
      "自我模型：认知负荷（cognitive_load）",
      "自我模型：稳定性（stability_level）",
      "自我模型：自信度漂移（confidence_drift）",
      "自我模型：近期弱点（recent_weaknesses）",
      "推理预算余量（compute/token/time_remaining_ratio）",
    ],
    outputs: [
      "评估风格（evaluation_style）",
      "风险容忍度（risk_tolerance）",
      "行动节奏（action_rhythm）",
      "确认策略（confirmation_strategy）",
      "进化方向（evolution_direction）",
    ],
  },
};

interface NineQuestionIntroCardProps {
  questionId: string;
}

/**
 * 九问介绍卡片组件
 * 使用表格方式展示问题的目标、期望数据和最终输出
 */
export default function NineQuestionIntroCard({ questionId }: NineQuestionIntroCardProps) {
  const intro = NINE_QUESTIONS_INTRO[questionId];

  if (!intro) {
    return null;
  }

  const SectionRows = ({ title, items }: { title: string; items: string[] }) => (
    <Box sx={{ border: 1, borderColor: "divider", borderRadius: 1, overflow: "hidden" }}>
      <Box
        sx={{
          px: 2,
          py: 1.5,
          bgcolor: "action.hover",
          color: "text.primary",
          fontWeight: 700,
          WebkitTextFillColor: (theme) => theme.palette.text.primary,
        }}
      >
        {title}
      </Box>
      <Stack spacing={0} divider={<Box sx={{ borderTop: 1, borderColor: "divider" }} />}>
        {items.map((item, index) => (
          <Box
            key={`${title}-${index}`}
            sx={{
              px: 2,
              py: 1.5,
              color: "text.primary",
              WebkitTextFillColor: (theme) => theme.palette.text.primary,
              wordBreak: "break-word",
            }}
          >
            {item}
          </Box>
        ))}
      </Stack>
    </Box>
  );

  return (
    <Card variant="outlined" sx={{ mb: 3, bgcolor: "info.50", borderColor: "info.main" }}>
      <CardContent>
        <Typography variant="h6" gutterBottom color="info.main" fontWeight="bold">
          📖 {intro.title} - 问题说明
        </Typography>

        <Stack spacing={2}>
          <SectionRows title="🎯 目标" items={intro.goals} />
          <SectionRows title="📊 期望获得的数据" items={intro.expectedData} />
          <SectionRows title="✨ 最终输出" items={intro.outputs} />
        </Stack>
      </CardContent>
    </Card>
  );
}
