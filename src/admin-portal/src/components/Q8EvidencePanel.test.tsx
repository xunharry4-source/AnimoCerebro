import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Q8EvidencePanel from "./Q8EvidencePanel";

describe("Q8EvidencePanel", () => {
  it("shows only abstract intent fields and separates internal and external Q8 intents", () => {
    render(
      <Q8EvidencePanel
        evidence={
          {
            aggregated_context: { q1_to_q7_snapshot: {}, absolute_red_line_count: 0, capability_ceiling_count: 0 },
            runtime_state: { persistent_task_state: [], cognitive_agenda: [] },
          } as any
        }
        inference={
          {
            objective_profile: {
              current_primary_objective: "生成真实任务",
              current_phase_tasks: [],
              priority_order: [],
            },
            task_queue: {
              next_self_tasks: [],
              blocked_self_tasks: [],
              proactive_actions: [],
            },
            q8_internal_cognitive_tasks: [
              {
                intent_name: "整理反思记录",
                intent_description: "写入内部反思和学习记录",
                creation_rationale: "内部自我迭代需要补齐记录",
                required_capability: "reflection_synthesis",
              },
            ],
            q8_external_execution_tasks: [
              {
                intent_name: "调用 Gemini CLI 检查文件",
                intent_description: "通过外部 CLI 执行文件检查",
                creation_rationale: "需要外部 CLI 能力",
                required_capability: "host_cli_execution",
              },
            ],
          } as any
        }
      />,
    );

    const root = screen.getByTestId("q8-created-task-list");
    expect(root).toHaveTextContent("整理反思记录");
    expect(root).toHaveTextContent("写入内部反思和学习记录");
    expect(root).toHaveTextContent("内部自我迭代需要补齐记录");
    expect(root).toHaveTextContent("调用 Gemini CLI 检查文件");
    expect(root).toHaveTextContent("通过外部 CLI 执行文件检查");
    expect(root).toHaveTextContent("需要外部 CLI 能力");

    const internalRows = screen.getAllByTestId("q8-created-task-internal");
    const externalRows = screen.getAllByTestId("q8-created-task-external");
    expect(internalRows).toHaveLength(1);
    expect(externalRows).toHaveLength(1);
    expect(within(internalRows[0]).getByText("整理反思记录")).toBeInTheDocument();
    expect(within(externalRows[0]).getByText("调用 Gemini CLI 检查文件")).toBeInTheDocument();

    expect(root).not.toHaveTextContent("current_primary_objective");
    expect(root).not.toHaveTextContent("q1_to_q7_snapshot");
    expect(root).not.toHaveTextContent("raw_payload");
  });

  it("renders Q8 business task_description, creation_reason, and created time fields", () => {
    render(
      <Q8EvidencePanel
        evidence={
          {
            aggregated_context: { q1_to_q7_snapshot: {}, absolute_red_line_count: 0, capability_ceiling_count: 0 },
            runtime_state: { persistent_task_state: [], cognitive_agenda: [] },
          } as any
        }
        inference={
          {
            objective_profile: {
              current_primary_objective: "生成真实 Q8 任务",
              current_phase_tasks: [],
              priority_order: [],
            },
            task_queue: {
              next_self_tasks: [],
              blocked_self_tasks: [],
              proactive_actions: [],
            },
            q8_internal_cognitive_tasks: [
              {
                task_id: "q8-business-field-task",
                intent_name: "修复 Q8 任务表格展示",
                intent_description: "必须展示真实任务说明字段内容",
                creation_rationale: "Q8 根据当前目标生成页面修复任务",
                createdAt: "2026-05-01T09:30:00Z",
                required_capability: "ui_fix",
              },
            ],
            q8_external_execution_tasks: [
              {
                task_id: "q8-metadata-field-task",
                intent_name: "校验 Q8 抽象意图原始载荷",
                metadata: {
                  raw_payload: {
                    intent_description: "从 Q8 raw_payload 读取任务说明",
                    creation_rationale: "原始载荷保存了真实创建原因",
                    created_at: "2026-05-01T10:45:00Z",
                    task_type: "api_validation",
                  },
                },
              },
            ],
          } as any
        }
      />,
    );

    const root = screen.getByTestId("q8-created-task-list");
    expect(root).toHaveTextContent("必须展示真实任务说明字段内容");
    expect(root).toHaveTextContent("Q8 根据当前目标生成页面修复任务");
    expect(root).toHaveTextContent("2026");
    expect(root).toHaveTextContent("从 Q8 raw_payload 读取任务说明");
    expect(root).toHaveTextContent("原始载荷保存了真实创建原因");
    expect(root).not.toHaveTextContent("暂无任务说明");
    expect(root).not.toHaveTextContent("暂无创建原因");
  });
});
