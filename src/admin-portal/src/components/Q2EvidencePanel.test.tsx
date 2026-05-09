import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Q2EvidencePanel from "./Q2EvidencePanel";

describe("Q2EvidencePanel", () => {
  it("renders asset inventory and resource evaluation", () => {
    render(
      <Q2EvidencePanel
        evidence={
          {
            workspace_permission: {
              available_workspaces: ["/console/workspaces"],
            },
            tools_agents: {
              unified_inventory: {},
            },
            memory_strategy: {},
            asset_inventory: {},
          } as any
        }
        inference={{
          asset_inventory: {
            inventory_summary: "当前资产指向控制台研发和插件工具链审计领域。",
            cognitive_and_functional_tools: [{
              asset_name: "plugin-registry",
              description: "已注册真实工具链",
              source: "Internal_Plugin",
              plugin_category: "Cognitive",
              trust_level: "high",
              validity: "permanent",
            }],
          },
          sufficiency_assessment: {
            resource_status: "sufficient",
            missing_critical_assets: [],
            bottleneck_node: "none",
          },
        } as any}
      />,
    );

    expect(screen.getByText("Q2 AssetInventory")).toBeInTheDocument();
    expect(screen.getByText("已注册真实工具链")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /资源评估/ }));
    expect(screen.getByText("sufficient")).toBeInTheDocument();
  });

  it("falls back to evidence asset inventory when inference asset inventory is empty", () => {
    render(
      <Q2EvidencePanel
        evidence={
          {
            workspace_permission: {},
            tools_agents: {},
            memory_strategy: {},
            asset_inventory: {
              inventory_summary: "当前资产指向 evidence 回填的工具链审计领域。",
              cognitive_and_functional_tools: [{
                asset_name: "fallback-tool-registry",
                description: "从 evidence 分区回填的工具资产",
                source: "Internal_Plugin",
                plugin_category: "Cognitive",
                trust_level: "high",
                validity: "permanent",
              }],
            },
          } as any
        }
        inference={{
          asset_inventory: {},
          sufficiency_assessment: {
            resource_status: "sufficient",
            missing_critical_assets: [],
            bottleneck_node: "none",
          },
        } as any}
      />,
    );

    expect(screen.getByText("fallback-tool-registry")).toBeInTheDocument();
    expect(screen.getByText("从 evidence 分区回填的工具资产")).toBeInTheDocument();
  });

  it("shows both cognitive and functional internal plugins in the plugin tab", () => {
    render(
      <Q2EvidencePanel
        evidence={
          {
            workspace_permission: {},
            tools_agents: {
              humanized_inventory: {
                cognitive_tool_rows: [{ id: "nine-question-q2", description: "Q2 认知盘点插件" }],
                execution_tool_rows: [{ id: "office_docx_modifier", description: "功能插件：编辑 Word 文档" }],
              },
            },
            memory_strategy: {},
            asset_inventory: {
              inventory_summary: "当前资产指向插件工具链审计领域。",
            },
          } as any
        }
        inference={{
          asset_inventory: {},
          sufficiency_assessment: {
            resource_status: "sufficient",
            missing_critical_assets: [],
            bottleneck_node: "none",
          },
        } as any}
      />,
    );

    fireEvent.click(screen.getByRole("tab", { name: /内部插件/ }));

    expect(screen.getByText("认知插件")).toBeInTheDocument();
    expect(screen.getByText("nine-question-q2")).toBeInTheDocument();
    expect(screen.getByText("功能插件")).toBeInTheDocument();
    expect(screen.getByText("office_docx_modifier")).toBeInTheDocument();
    expect(screen.getByText("功能插件：编辑 Word 文档")).toBeInTheDocument();
  });
});
