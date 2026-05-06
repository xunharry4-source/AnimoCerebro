import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Q7EvidencePanel from "./Q7EvidencePanel";

describe("Q7EvidencePanel", () => {
  it("renders Q7 red-line constraints in a high-priority gavel alert", () => {
    render(
      <Q7EvidencePanel
        evidence={
          {
            identity_kernel_constraints: ["dynamic goals cannot override identity locks"],
            authorization_boundary_constraints: ["requires_human_confirmation=true"],
            safety_rejection_history: ["G12 rejected force write"],
            procedural_memory_constraints: ["do not bypass cloud audit"],
            non_bypassable_constraints: ["DO_NOT_BYPASS_CLOUD_AUDIT"],
            ban_source_explanations: ["IdentityKernel and G12 SafetyGate"],
            question_driver_refs: ["Q5", "IdentityKernel", "G12"],
          } as any
        }
        inference={
          {
            current_red_line_hits: ["External write would bypass confirmation"],
            rejected_operation_records: ["G12 rejected force write"],
            ban_source_explanations: ["G12 SafetyGate rejected the high-risk operation"],
            non_bypassable_constraints: ["DO_NOT_BYPASS_CLOUD_AUDIT"],
            question_driver_refs: ["Q5", "G12"],
          } as any
        }
      />,
    );

    const alert = screen.getByTestId("q7-red-line-alert");
    expect(alert).toHaveTextContent("Q7 红线与不可绕过约束");
    expect(alert).toHaveTextContent("DO_NOT_BYPASS_CLOUD_AUDIT");
    expect(screen.getByTestId("q7-non-bypassable-constraints")).toHaveTextContent("DO_NOT_BYPASS_CLOUD_AUDIT");
    expect(screen.getByText("当前红线命中")).toBeInTheDocument();
    expect(screen.getByText("External write would bypass confirmation")).toBeInTheDocument();
  });
});
