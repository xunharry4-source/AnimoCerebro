import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Q2Detail from "./Q2Detail";
import * as api from "../nineQuestionsApi";

vi.mock("../nineQuestionsApi", async () => {
  const actual = await vi.importActual("../nineQuestionsApi");
  return {
    ...actual,
    fetchNineQuestionDetail: vi.fn(),
    fetchNineQuestionSummary: vi.fn(),
    fetchNineQuestionEvidence: vi.fn(),
    fetchNineQuestionInference: vi.fn(),
    fetchNineQuestionTracePayload: vi.fn(),
    fetchNineQuestionRaw: vi.fn(),
    fetchNineQuestionModules: vi.fn(),
  };
});

describe("Q2Detail business tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows role identity business values from partitioned Q2 results and exposes malformed evidence as warnings instead of crashing", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockRejectedValue(new Error("legacy detail endpoint should not be used"));
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({
      status: "completed",
      question_id: "q2",
    } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({
      q1_summary: {
        primary_domain: "production_server",
        secondary_domains: "bad-secondary-domains",
        uncertainties: ["missing workspace metadata"],
        risk_summary: "Current session looks production-bound.",
      },
      identity_kernel: {
        meta_motivation: "Protect mission continuity",
        values_prohibition: "Do not fake authority",
        non_bypassable_constraints: "bad-constraints-type",
      },
      manual_intervention: "bad-manual-intervention",
    } as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue({
      role_profile: {
        identity_role: "Operator",
        active_role: "ProductionGuardian",
        task_role: "StabilityAuditor",
      },
      mission_boundary: {
        current_mission: "Stabilize runtime decisions",
        priority_duties: ["Contain instability", "Preserve audit trail"],
        continuity_boundaries: ["No fake green", "No silent fallback"],
      },
    } as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({
      provider_name: "provider-tools-default",
      elapsed_ms: 73,
      token_usage: { input_tokens: 20, output_tokens: 8, total_tokens: 28 },
      context_data: {},
    } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q2-business",
      tool_id: "nine_questions.q2",
      mounted_plugins: [],
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: { status: "completed" },
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q2"]}>
        <Routes>
          <Route path="/console/nine-questions/q2" element={<Q2Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q2-detail-root")).toBeInTheDocument();
    });

    expect(screen.getByTestId("q2-active-role-chip")).toHaveTextContent("ProductionGuardian");
    expect(screen.getByText(/✅ 已推演角色: StabilityAuditor/)).toBeInTheDocument();
    expect(screen.getAllByText(/Stabilize runtime decisions/).length).toBeGreaterThan(0);
    expect(screen.getByText(/q1_summary.secondary_domains 字段类型异常/)).toBeInTheDocument();
    expect(screen.getByText(/identity_kernel.non_bypassable_constraints 字段类型异常/)).toBeInTheDocument();
    expect(screen.getByText(/Q2 原始字段诊断/)).toBeInTheDocument();
  });
});
