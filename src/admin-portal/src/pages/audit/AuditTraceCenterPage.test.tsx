import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import AuditTraceCenterPage from "./AuditTraceCenterPage";

describe("AuditTraceCenterPage", () => {
  it("shows audit start points as a table with workflow/table entry links", () => {
    render(
      <MemoryRouter>
        <AuditTraceCenterPage />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("audit-trace-center-page")).toBeInTheDocument();
    expect(screen.getByTestId("audit-trace-start-table")).toBeInTheDocument();
    expect(screen.getByTestId("audit-trace-mode-card-nine_questions")).toHaveTextContent("基于 9 问开始的审计与溯源");
    expect(screen.getByTestId("audit-trace-mode-card-reflection")).toHaveTextContent("基于反思开始的审计与溯源");
    expect(screen.getByTestId("audit-trace-mode-card-learning")).toHaveTextContent("基于学习开始的审计与溯源");
    expect(screen.getAllByRole("link", { name: "工作流查看" })[0]).toHaveAttribute("href", "/console/audit/nine_questions/workflow");
    expect(screen.getAllByRole("link", { name: "表格查看" })[0]).toHaveAttribute("href", "/console/audit/nine_questions/table");
  });
});
