import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AuditReviewLedgerPage from "./AuditReviewLedgerPage";

describe("AuditReviewLedgerPage", () => {
  it("shows the upstream merge review warning and overlap files", () => {
    render(<AuditReviewLedgerPage />);

    expect(screen.getByTestId("audit-review-ledger-page")).toBeInTheDocument();
    expect(screen.getByText(/2026-04-20 已吸收上游 `8145d0b`/)).toBeInTheDocument();
    expect(screen.getByText("已复查上游 8145d0b")).toBeInTheDocument();
    expect(screen.getByText("Q2/Q6/Q8/Q9 需持续复查")).toBeInTheDocument();
    expect(screen.getByText("src/zentex/nine_questions/query.py")).toBeInTheDocument();
    expect(screen.getByText("src/plugins/nine_questions/q8_what_should_i_do_now/q8_what_should_i_do_now_plugin.py")).toBeInTheDocument();
  });
});
