import {
  Alert,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";

type AnswerRow = {
  label: string;
  value: unknown;
};

function asRecord(value: unknown): Record<string, any> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, any>) : {};
}

function assetListSummary(value: unknown): string {
  if (!Array.isArray(value) || value.length === 0) return "";
  return value
    .map((rawItem) => {
      const item = asRecord(rawItem);
      return String(item.asset_name || item.description || item.source || "").trim();
    })
    .filter(Boolean)
    .slice(0, 3)
    .join(", ");
}

function pickFirst(...values: unknown[]): unknown {
  return values.find((value) => {
    if (Array.isArray(value)) return value.length > 0;
    if (value && typeof value === "object") return Object.keys(value as Record<string, any>).length > 0;
    return value !== null && value !== undefined && String(value).trim() !== "";
  });
}

function renderValue(value: unknown) {
  if (Array.isArray(value)) {
    return value.length > 0 ? value.map((item) => formatValue(item)).join("；") : "无";
  }
  return formatValue(value);
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "N/A";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "N/A";
  if (typeof value === "string") return value;
  if (typeof value === "object") {
    const record = asRecord(value);
    const preferred = pickFirst(
      record.label,
      record.name,
      record.title,
      record.strategy,
      record.action,
      record.description,
      record.reason,
      record.status,
    );
    return preferred ? String(preferred) : JSON.stringify(value);
  }
  return String(value);
}

function buildRows(questionId: string, inference: Record<string, any>, result: Record<string, any>): AnswerRow[] {
  const source = Object.keys(inference).length > 0 ? inference : result;
  const q2Assessment = asRecord(source.sufficiency_assessment);
  const q2Assets = asRecord(source.asset_inventory);
  const q3Role = asRecord(source.role_profile);
  const q3Mission = asRecord(source.mission_boundary);

  const rowsByQuestion: Record<string, AnswerRow[]> = {
    q1: [
      { label: "当前环境主领域", value: source.primary_domain },
      { label: "当前环境次领域", value: source.secondary_domains },
      { label: "置信度", value: source.confidence },
      { label: "LLM 分析结论", value: source.reasoning_summary },
      { label: "不确定性", value: source.uncertainties },
      { label: "建议第一步", value: source.suggested_first_step },
    ],
    q2: [
      { label: "资产领域侧写", value: q2Assets.inventory_summary },
      { label: "资源状态", value: pickFirst(q2Assessment.resource_status_label, q2Assessment.resource_status) },
      { label: "缺失关键资产", value: q2Assessment.missing_critical_assets },
      { label: "瓶颈节点", value: q2Assessment.bottleneck_node },
      { label: "可用工具", value: assetListSummary(q2Assets.cognitive_and_functional_tools) },
      { label: "外部 Agent", value: assetListSummary(q2Assets.connected_agents) },
    ],
    q3: [
      { label: "身份角色", value: q3Role.identity_role },
      { label: "当前活跃角色", value: q3Role.active_role },
      { label: "系统推断参考角色", value: q3Role.inferred_reference_role },
      { label: "角色适配度偏差", value: q3Role.role_alignment_gap },
      { label: "任务角色", value: q3Role.task_role },
      { label: "当前使命", value: q3Mission.current_mission },
      { label: "优先职责", value: q3Mission.priority_duties },
      { label: "连续性边界", value: q3Mission.continuity_boundaries },
    ],
    q4: [
      { label: "能力上限", value: source.capability_upper_limits },
      { label: "可行动空间", value: source.actionable_space },
      { label: "可执行策略", value: source.executable_strategies },
    ],
    q5: [
      { label: "执行层级", value: source.execution_tier },
      { label: "交互范围", value: source.interaction_scope },
      { label: "需要人工确认", value: source.requires_human_confirmation },
      { label: "需要云审计", value: source.requires_cloud_audit },
      { label: "明确禁止操作", value: source.explicitly_forbidden_actions },
      { label: "合规风险", value: source.compliance_risks },
      { label: "允许委托目标", value: source.allowed_delegation_targets },
    ],
    q6: [
      { label: "绝对红线", value: source.absolute_red_lines },
      { label: "性能权衡禁令", value: source.performance_tradeoff_bans },
      { label: "禁止策略", value: source.prohibited_strategies },
      { label: "污染风险", value: source.contamination_risks },
    ],
    q7: [
      { label: "当前红线命中", value: source.current_red_line_hits },
      { label: "拒绝操作记录", value: source.rejected_operation_records },
      { label: "禁令来源说明", value: source.ban_source_explanations },
      { label: "不可绕过约束", value: source.non_bypassable_constraints },
      { label: "引用来源", value: source.question_driver_refs },
    ],
    q9: [
      { label: "评估风格", value: source.evaluation_style },
      { label: "风险容忍度", value: source.risk_tolerance },
      { label: "行动节奏", value: source.action_rhythm },
      { label: "确认策略", value: source.confirmation_strategy },
      { label: "进化方向", value: source.evolution_direction },
    ],
  };

  return (rowsByQuestion[questionId] || []).filter((row) => {
    if (Array.isArray(row.value)) return row.value.length > 0;
    return row.value !== null && row.value !== undefined && String(row.value).trim() !== "";
  });
}

export default function NineQuestionAnswerTable({
  questionId,
  inference,
  result,
}: {
  questionId: string;
  inference: unknown;
  result?: unknown;
}) {
  const rows = buildRows(questionId, asRecord(inference), asRecord(result));

  return (
    <Card variant="outlined" sx={{ mb: 3 }} data-testid={`${questionId}-answer-table-card`}>
      <CardContent>
        <Typography variant="h6" gutterBottom fontWeight="bold">
          {questionId.toUpperCase()} 问题回答结果
        </Typography>
        {rows.length === 0 ? (
          <Alert severity="warning" data-testid={`${questionId}-answer-table-empty`}>
            当前没有可展示的问题回答结果。
          </Alert>
        ) : (
          <TableContainer>
            <Table size="small" data-testid={`${questionId}-answer-table`}>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ width: "28%", fontWeight: "bold" }}>回答项</TableCell>
                  <TableCell sx={{ fontWeight: "bold" }}>回答内容</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.label} hover>
                    <TableCell sx={{ verticalAlign: "top" }}>{row.label}</TableCell>
                    <TableCell sx={{ verticalAlign: "top" }}>
                      <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                        {renderValue(row.value)}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </CardContent>
    </Card>
  );
}
