import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Q2DataTabs from "./Q2DataTabs";

describe("Q2DataTabs", () => {
  it("shows every available tool in the output summary", () => {
    render(
      <Q2DataTabs
        evidence={null}
        inference={
          {
            asset_inventory: {
              inventory_summary: "当前资产包含完整内部功能插件清单。",
              long_term_memory: [],
              cognitive_and_functional_tools: [
                { asset_name: "functional-plugin-1" },
                { asset_name: "functional-plugin-2" },
                { asset_name: "functional-plugin-3" },
                { asset_name: "functional-plugin-4" },
              ],
              connected_agents: [],
              strategy_patches: [],
            },
            sufficiency_assessment: {
              resource_status: "sufficient",
              missing_critical_assets: [],
              bottleneck_node: "none",
            },
          } as any
        }
      />,
    );

    fireEvent.click(screen.getByRole("tab", { name: "输出结果" }));

    expect(screen.getByText(/4 项：functional-plugin-1/)).toBeInTheDocument();
    expect(screen.getByText(/functional-plugin-4/)).toBeInTheDocument();
  });
});
