import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import SimulationExplorer from "./SimulationExplorer";

describe("SimulationExplorer", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          json: async () => ({
            bundle: {
              goal_id: "goal-runtime-stability",
              status: "completed",
              branches: [
                {
                  branch_id: "branch-a",
                  branch_label: "保守修复路径",
                  target_domain: "general",
                  predicted_impacts: ["优先稳定 replay 链路"],
                  risk_score: 0.2,
                  failure_cascade: false,
                  simulated_by: ["simulation-thought-sandbox"],
                },
                {
                  branch_id: "branch-b",
                  branch_label: "激进扩展路径",
                  target_domain: "market",
                  predicted_impacts: ["存在灾难性失败级联风险"],
                  risk_score: 0.92,
                  failure_cascade: true,
                  veto_reason: "Projected failure cascade under degraded runtime",
                  simulated_by: ["simulation-market-impact"],
                },
              ],
              outcome_comparison: {
                summary: "保守修复路径风险最低。",
                risk_ranking: [
                  { branch_id: "branch-a", risk_score: 0.2, rank: 1 },
                  { branch_id: "branch-b", risk_score: 0.92, rank: 2 },
                ],
                recommended_branch_id: "branch-a",
              },
            },
          }),
        } satisfies Partial<Response> as Response)
      )
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    globalThis.fetch = originalFetch;
  });

  it("renders horizontal branch comparison cards from the real API payload", async () => {
    render(<SimulationExplorer />);

    fireEvent.change(screen.getByLabelText("目标编号"), {
      target: { value: "goal-runtime-stability" },
    });
    fireEvent.click(screen.getByRole("button", { name: "刷新预演" }));

    await waitFor(() => {
      expect(screen.getAllByTestId("simulation-branch-card")).toHaveLength(2);
    });

    expect(screen.getByText("保守修复路径")).toBeInTheDocument();
    expect(screen.getByText("激进扩展路径")).toBeInTheDocument();
    expect(screen.getByText("灾难性失败级联")).toBeInTheDocument();
    expect(screen.getByText("推荐分支：保守修复路径")).toBeInTheDocument();
  });
});
